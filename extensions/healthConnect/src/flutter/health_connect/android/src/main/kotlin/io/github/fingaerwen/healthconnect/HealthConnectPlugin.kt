package io.github.fingaerwen.healthconnect

import android.app.Activity
import android.content.Context
import android.content.Intent
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.ActiveCaloriesBurnedRecord
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.records.TotalCaloriesBurnedRecord
import androidx.health.connect.client.request.AggregateGroupByPeriodRequest
import androidx.health.connect.client.time.TimeRangeFilter
import io.flutter.embedding.engine.plugins.FlutterPlugin
import io.flutter.embedding.engine.plugins.activity.ActivityAware
import io.flutter.embedding.engine.plugins.activity.ActivityPluginBinding
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import io.flutter.plugin.common.PluginRegistry
import java.time.LocalDate
import java.time.Period
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Bridge between the Dart side (health_connect_service.dart) and Android Health Connect (plan HC1.1): its status,
 * the three read permissions, and each local day's totals of steps, active calories and total calories. Health
 * Connect's totals don't count overlapping sources twice. Talon only reads, never writes.
 */
class HealthConnectPlugin :
    FlutterPlugin, MethodChannel.MethodCallHandler, ActivityAware, PluginRegistry.ActivityResultListener {

    private lateinit var channel: MethodChannel
    private lateinit var appContext: Context
    private var activityBinding: ActivityPluginBinding? = null
    private var activity: Activity? = null
    private var pendingAsk: MethodChannel.Result? = null
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private val askRequestCode = 4721

    override fun onAttachedToEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        appContext = binding.applicationContext
        channel = MethodChannel(binding.binaryMessenger, "io.github.fingaerwen/healthConnect") // same name as in Dart
        channel.setMethodCallHandler(this)
    }

    override fun onDetachedFromEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        channel.setMethodCallHandler(null)
        scope.cancel()
    }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "status" -> result.success(status())
            "hasPermissions" -> scope.launch {
                try {
                    if (status() != "available") {
                        result.success(false)
                        return@launch
                    }
                    val granted = withContext(Dispatchers.IO) { client().permissionController.getGrantedPermissions() }
                    result.success(granted.containsAll(permissions))
                } catch (problem: Exception) {
                    result.error("healthConnect", describe(problem), null)
                }
            }
            "requestPermissions" -> askForPermissions(result)
            "readDays" -> scope.launch { readDays(call.argument<String>("from"), call.argument<String>("to"), result) }
            else -> result.notImplemented()
        }
    }

    /** "available", "needsUpdate" (Health Connect wants an update first) or "unavailable". */
    private fun status(): String = when (HealthConnectClient.getSdkStatus(appContext)) {
        HealthConnectClient.SDK_AVAILABLE -> "available"
        HealthConnectClient.SDK_UNAVAILABLE_PROVIDER_UPDATE_REQUIRED -> "needsUpdate"
        else -> "unavailable"
    }

    private fun client(): HealthConnectClient = HealthConnectClient.getOrCreate(appContext)

    /** Health Connect's own screen asks for the three permissions. Answers true once all three are allowed. */
    private fun askForPermissions(result: MethodChannel.Result) {
        val screen = activity
        if (screen == null) {
            result.error("noScreen", "Talon isn't on screen, so Health Connect can't ask", null)
            return
        }
        if (status() != "available") {
            result.success(false)
            return
        }
        pendingAsk?.success(false) // an earlier ask that never came back: answer it, so it doesn't hang
        pendingAsk = result
        try {
            screen.startActivityForResult(contract.createIntent(screen, permissions), askRequestCode)
        } catch (problem: Exception) {
            pendingAsk = null
            result.error("healthConnect", describe(problem), null)
        }
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?): Boolean {
        if (requestCode != askRequestCode) return false
        val granted = try {
            contract.parseResult(resultCode, data)
        } catch (_: Exception) {
            emptySet()
        }
        pendingAsk?.success(granted.containsAll(permissions))
        pendingAsk = null
        return true
    }

    /** Each local day from `from` to `to` (both included), with Health Connect's totals, null for what it has none of. */
    private suspend fun readDays(from: String?, to: String?, result: MethodChannel.Result) {
        try {
            val first = LocalDate.parse(from)
            val last = LocalDate.parse(to)
            val buckets = withContext(Dispatchers.IO) {
                client().aggregateGroupByPeriod(
                    AggregateGroupByPeriodRequest(
                        metrics = setOf(
                            StepsRecord.COUNT_TOTAL,
                            ActiveCaloriesBurnedRecord.ACTIVE_CALORIES_TOTAL,
                            TotalCaloriesBurnedRecord.ENERGY_TOTAL,
                        ),
                        timeRangeFilter = TimeRangeFilter.between(first.atStartOfDay(), last.plusDays(1).atStartOfDay()),
                        timeRangeSlicer = Period.ofDays(1),
                    )
                )
            }
            result.success(buckets.map { bucket ->
                mapOf(
                    "date" to bucket.startTime.toLocalDate().toString(),
                    "steps" to bucket.result[StepsRecord.COUNT_TOTAL],
                    "activeKcal" to bucket.result[ActiveCaloriesBurnedRecord.ACTIVE_CALORIES_TOTAL]?.inKilocalories,
                    "totalKcal" to bucket.result[TotalCaloriesBurnedRecord.ENERGY_TOTAL]?.inKilocalories,
                )
            })
        } catch (problem: Exception) {
            result.error("healthConnect", describe(problem), null)
        }
    }

    /** A problem in a few words for the app's log: its kind and message, never any health data. */
    private fun describe(problem: Exception): String = "${problem.javaClass.simpleName}: ${problem.message ?: ""}".take(200)

    override fun onAttachedToActivity(binding: ActivityPluginBinding) = attachTo(binding)

    override fun onDetachedFromActivityForConfigChanges() = detach()

    override fun onReattachedToActivityForConfigChanges(binding: ActivityPluginBinding) = attachTo(binding)

    override fun onDetachedFromActivity() {
        detach()
        pendingAsk?.success(false) // the screen is gone for good, so Health Connect's answer can't reach us
        pendingAsk = null
    }

    private fun attachTo(binding: ActivityPluginBinding) {
        activityBinding = binding
        activity = binding.activity
        binding.addActivityResultListener(this)
    }

    private fun detach() {
        activityBinding?.removeActivityResultListener(this)
        activityBinding = null
        activity = null
    }

    companion object {
        /** The three things Talon reads (HC1.1). */
        val permissions = setOf(
            HealthPermission.getReadPermission(StepsRecord::class),
            HealthPermission.getReadPermission(ActiveCaloriesBurnedRecord::class),
            HealthPermission.getReadPermission(TotalCaloriesBurnedRecord::class),
        )
        private val contract = PermissionController.createRequestPermissionResultContract()
    }
}
