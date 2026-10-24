package io.github.fingaerwen.weighinnotify

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.ActivityCompat
import io.flutter.embedding.engine.plugins.FlutterPlugin
import io.flutter.embedding.engine.plugins.activity.ActivityAware
import io.flutter.embedding.engine.plugins.activity.ActivityPluginBinding
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import io.flutter.plugin.common.PluginRegistry

/** Bridge between the Dart side (weigh_in_notify_service.dart) and Android: one method per request name. */
class WeighInNotifyPlugin :
    FlutterPlugin, MethodChannel.MethodCallHandler, ActivityAware, PluginRegistry.RequestPermissionsResultListener {

    private lateinit var channel: MethodChannel
    private lateinit var appContext: Context
    private var activityBinding: ActivityPluginBinding? = null
    private var pendingPermissionResult: MethodChannel.Result? = null
    private val permissionRequestCode = 4711

    override fun onAttachedToEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        appContext = binding.applicationContext
        channel = MethodChannel(binding.binaryMessenger, "io.github.fingaerwen/weighInNotify") // same name as in Dart
        channel.setMethodCallHandler(this)
    }

    override fun onDetachedFromEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        channel.setMethodCallHandler(null)
    }

    /** Reads a string argument (empty if missing). */
    private fun MethodCall.text(key: String): String = argument<String>(key) ?: ""

    /** Reads a number argument as Int (Dart may send Int or Long). */
    private fun MethodCall.number(key: String): Int = (argument<Number>(key) ?: 0).toInt()

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "requestPermission" -> requestPermission(result)
            "showNow" -> result.success(
                WeighInScheduler.showNotification(appContext, call.text("title"), call.text("body"), WeighInScheduler.showNowNotificationId)
            )
            "scheduleInSeconds" -> {
                val triggerAt = System.currentTimeMillis() + call.number("seconds") * 1000L
                WeighInScheduler.setAlarm(appContext, triggerAt, WeighInScheduler.oneOffRequestCode, call.text("title"), call.text("body"), WeighInScheduler.kindOneOff)
                result.success(WeighInScheduler.formatTime(triggerAt))
            }
            "scheduleWeekly" -> {
                WeighInScheduler.saveWeekly(appContext, call.number("isoWeekday"), call.number("hour"), call.number("minute"), call.text("title"), call.text("body"))
                val next = WeighInScheduler.rescheduleWeeklyFromPrefs(appContext)
                result.success(next?.let { WeighInScheduler.formatTime(it) })
            }
            "cancelWeekly" -> {
                WeighInScheduler.cancelWeekly(appContext)
                result.success(true)
            }
            "scheduleDaily" -> {
                WeighInScheduler.saveDaily(appContext, call.number("hour"), call.number("minute"), call.text("title"), call.text("body"))
                val next = WeighInScheduler.rescheduleDailyFromPrefs(appContext)
                result.success(next?.let { WeighInScheduler.formatTime(it) })
            }
            "cancelDaily" -> {
                WeighInScheduler.cancelDaily(appContext)
                result.success(true)
            }
            "getStatus" -> result.success(
                mapOf(
                    "notificationsAllowed" to WeighInScheduler.notificationsAllowed(appContext),
                    "exactAlarms" to WeighInScheduler.canUseExactAlarms(appContext),
                    "weeklyNext" to WeighInScheduler.nextWeeklyMillis(appContext)?.let { WeighInScheduler.formatTime(it) },
                    "dailyNext" to WeighInScheduler.nextDailyMillis(appContext)?.let { WeighInScheduler.formatTime(it) },
                    "androidSdk" to Build.VERSION.SDK_INT,
                )
            )
            else -> result.notImplemented()
        }
    }

    /** Android 13+ asks the user to allow notifications; older versions allow them by default. */
    private fun requestPermission(result: MethodChannel.Result) {
        if (Build.VERSION.SDK_INT < 33 ||
            ActivityCompat.checkSelfPermission(appContext, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
        ) {
            result.success(WeighInScheduler.notificationsAllowed(appContext))
            return
        }
        val activity = activityBinding?.activity
        if (activity == null || pendingPermissionResult != null) {
            result.success(false) // no screen to show the question on, or a question is already open
            return
        }
        pendingPermissionResult = result
        ActivityCompat.requestPermissions(activity, arrayOf(Manifest.permission.POST_NOTIFICATIONS), permissionRequestCode)
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray): Boolean {
        if (requestCode != permissionRequestCode) return false
        val granted = grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED
        pendingPermissionResult?.success(granted)
        pendingPermissionResult = null
        return true
    }

    // Keep track of the current screen (needed to show the permission question).
    override fun onAttachedToActivity(binding: ActivityPluginBinding) {
        activityBinding = binding
        binding.addRequestPermissionsResultListener(this)
    }

    override fun onDetachedFromActivityForConfigChanges() = onDetachedFromActivity()

    override fun onReattachedToActivityForConfigChanges(binding: ActivityPluginBinding) = onAttachedToActivity(binding)

    override fun onDetachedFromActivity() {
        activityBinding?.removeRequestPermissionsResultListener(this)
        activityBinding = null
    }
}
