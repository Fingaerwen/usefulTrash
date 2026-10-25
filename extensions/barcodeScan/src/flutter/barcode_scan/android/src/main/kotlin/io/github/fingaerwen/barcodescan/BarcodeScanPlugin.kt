package io.github.fingaerwen.barcodescan

import android.app.Activity
import android.content.Intent
import com.google.android.gms.common.api.ApiException
import com.google.android.gms.common.api.CommonStatusCodes
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.codescanner.GmsBarcodeScannerOptions
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning
import com.google.zxing.client.android.Intents
import com.google.zxing.integration.android.IntentIntegrator
import io.flutter.embedding.engine.plugins.FlutterPlugin
import io.flutter.embedding.engine.plugins.activity.ActivityAware
import io.flutter.embedding.engine.plugins.activity.ActivityPluginBinding
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import io.flutter.plugin.common.PluginRegistry
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Bridge between the Dart side (barcode_scan_service.dart) and two barcode scanners, to compare on the phone
 * (Ambrosia's Phase 0 check 1):
 * - "scanGoogle": Google's code scanner. The scanning runs inside Google Play services, so the app needs no
 *   camera permission; Google's library sends Google usage metrics (no images, no codes).
 * - "scanOpen": ZXing's scanner screen (open source), entirely inside the app, nothing over the network.
 *
 * Every request gets exactly one reply, including "cancelled" and every error: Flet method calls have no
 * default timeout, so a missing reply would leave the scan button waiting forever.
 */
class BarcodeScanPlugin : FlutterPlugin, MethodChannel.MethodCallHandler, ActivityAware,
    PluginRegistry.ActivityResultListener {

    private lateinit var channel: MethodChannel
    private var activity: Activity? = null  // the current screen; both scanners open on top of it
    private var activityBinding: ActivityPluginBinding? = null  // delivers ZXing's result
    private var pendingOpenScan: OneReply? = null  // the request waiting for ZXing's scanner screen

    override fun onAttachedToEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        channel = MethodChannel(binding.binaryMessenger, "io.github.fingaerwen/barcodeScan") // same name as in Dart
        channel.setMethodCallHandler(this)
    }

    override fun onDetachedFromEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        channel.setMethodCallHandler(null)
    }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        val reply = OneReply(result)
        try {
            when (call.method) {
                "scanGoogle" -> scanGoogle(reply)
                "scanOpen" -> scanOpen(reply)
                else -> reply.send(failure("unknownMethod", "No method called ${call.method}"))
            }
        } catch (e: Exception) {
            // Safety net: anything unexpected still gets an answer, so Python never waits forever.
            reply.send(failure(e.javaClass.simpleName, e.message))
        }
    }

    /** Google's scanner screen; replies with the barcode, "cancelled" or the error. */
    private fun scanGoogle(reply: OneReply) {
        val screen = activity
        if (screen == null) {
            reply.send(failure("noScreen", "No app screen to open the scanner on"))
            return
        }
        // Food packages only: fewer formats means faster, surer reads.
        val options = GmsBarcodeScannerOptions.Builder()
            .setBarcodeFormats(Barcode.FORMAT_EAN_13, Barcode.FORMAT_EAN_8, Barcode.FORMAT_UPC_A, Barcode.FORMAT_UPC_E)
            .build()
        GmsBarcodeScanning.getClient(screen, options).startScan()
            .addOnSuccessListener { barcode ->
                reply.send(mapOf("status" to "ok", "barcode" to barcode.rawValue.orEmpty(),
                                 "format" to googleFormatName(barcode.format)))
            }
            .addOnCanceledListener { reply.send(mapOf("status" to "cancelled")) }
            .addOnFailureListener { e ->
                // A closed scanner also arrives here on some versions, as a CANCELED status.
                if (e is ApiException && e.statusCode == CommonStatusCodes.CANCELED) {
                    reply.send(mapOf("status" to "cancelled"))
                } else {
                    reply.send(failure(e.javaClass.simpleName, e.message))
                }
            }
    }

    /** ZXing's scanner screen; its answer arrives in onActivityResult. */
    private fun scanOpen(reply: OneReply) {
        val screen = activity
        if (screen == null) {
            reply.send(failure("noScreen", "No app screen to open the scanner on"))
            return
        }
        // Only one scan at a time: an older request that never got its answer is answered now.
        pendingOpenScan?.send(failure("replaced", "A new scan started before this one finished"))
        pendingOpenScan = reply
        IntentIntegrator(screen)
            .setDesiredBarcodeFormats(IntentIntegrator.PRODUCT_CODE_TYPES)  // EAN-8/13, UPC-A/E and GS1 DataBar
            .setPrompt("Hold the barcode inside the frame")
            .setBeepEnabled(false)
            .setOrientationLocked(false)
            .initiateScan()
    }

    /** Receives ZXing's answer (registered through the activity binding). Other screens' answers aren't ours. */
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?): Boolean {
        if (requestCode != IntentIntegrator.REQUEST_CODE) return false
        val reply = pendingOpenScan ?: return true
        pendingOpenScan = null
        val result = IntentIntegrator.parseActivityResult(requestCode, resultCode, data)
        when {
            result?.contents != null ->
                reply.send(mapOf("status" to "ok", "barcode" to result.contents, "format" to (result.formatName ?: "")))
            data?.getBooleanExtra(Intents.Scan.MISSING_CAMERA_PERMISSION, false) == true ->
                reply.send(failure("noCamera", "The camera permission was refused"))
            else -> reply.send(mapOf("status" to "cancelled"))
        }
        return true
    }

    private fun googleFormatName(format: Int): String = when (format) {
        Barcode.FORMAT_EAN_13 -> "EAN_13"
        Barcode.FORMAT_EAN_8 -> "EAN_8"
        Barcode.FORMAT_UPC_A -> "UPC_A"
        Barcode.FORMAT_UPC_E -> "UPC_E"
        else -> "format $format"
    }

    /** A failure reply in the shape Python expects. */
    private fun failure(errorType: String, message: String?): Map<String, Any?> =
        mapOf("status" to "error", "errorType" to errorType, "message" to (message ?: ""))

    // Keep track of the current screen (both scanners open on top of it; ZXing's answer comes back through it).
    override fun onAttachedToActivity(binding: ActivityPluginBinding) = attachTo(binding)

    override fun onDetachedFromActivityForConfigChanges() = detachFromActivity()

    override fun onReattachedToActivityForConfigChanges(binding: ActivityPluginBinding) = attachTo(binding)

    override fun onDetachedFromActivity() {
        detachFromActivity()
        // The screen is gone for good, so ZXing's answer can't reach us: answer instead of hanging.
        pendingOpenScan?.send(failure("screenClosed", "The app screen closed before the scanner answered"))
        pendingOpenScan = null
    }

    private fun attachTo(binding: ActivityPluginBinding) {
        activityBinding = binding
        activity = binding.activity
        binding.addActivityResultListener(this)
    }

    private fun detachFromActivity() {
        activityBinding?.removeActivityResultListener(this)
        activityBinding = null
        activity = null
    }

    /** Answers a Flutter request exactly once: a second answer would crash the app, none would hang the button. */
    private class OneReply(private val result: MethodChannel.Result) {
        private val answered = AtomicBoolean(false)

        fun send(value: Any?) {
            if (answered.compareAndSet(false, true)) result.success(value)
        }
    }
}
