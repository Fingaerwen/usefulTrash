package io.github.fingaerwen.weighinnotify

import android.Manifest
import android.app.AlarmManager
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

/** All alarm + notification logic, shared by the plugin and the broadcast receivers. */
object WeighInScheduler {
    private const val channelId = "weighIn"
    private const val prefsName = "weighInNotify"
    const val weeklyRequestCode = 5001
    const val oneOffRequestCode = 5002
    const val showNowNotificationId = 5003
    const val extraTitle = "title"
    const val extraBody = "body"
    const val extraWeekly = "weekly"

    /** First moment matching the weekday/hour/minute that is strictly after [afterMillis] (local time, DST-safe). */
    fun nextWeeklyTrigger(isoWeekday: Int, hour: Int, minute: Int, afterMillis: Long): Calendar {
        val after = Calendar.getInstance().apply { timeInMillis = afterMillis }
        val target = (after.clone() as Calendar).apply {
            set(Calendar.HOUR_OF_DAY, hour)
            set(Calendar.MINUTE, minute)
            set(Calendar.SECOND, 0)
            set(Calendar.MILLISECOND, 0)
        }
        val calendarDay = isoWeekday % 7 + 1 // ISO 1=Monday..7=Sunday -> Calendar.MONDAY(2)..Calendar.SUNDAY(1)
        val daysAhead = (calendarDay - after.get(Calendar.DAY_OF_WEEK) + 7) % 7
        target.add(Calendar.DAY_OF_YEAR, daysAhead)
        if (!target.after(after)) target.add(Calendar.DAY_OF_YEAR, 7)
        return target
    }

    /** Records that the weekly alarm planned for [nextMillis] has just gone off (it must never fire twice). */
    fun markWeeklyFired(context: Context) {
        val prefs = context.getSharedPreferences(prefsName, Context.MODE_PRIVATE)
        prefs.edit().putLong("lastFiredMillis", prefs.getLong("nextMillis", 0L)).apply()
    }

    /** Human-readable local time, e.g. "2026-10-09 07:00". */
    fun formatTime(millis: Long): String = SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.US).format(Date(millis))

    /** True if exact alarms are allowed (always true below Android 12). */
    fun canUseExactAlarms(context: Context): Boolean {
        if (Build.VERSION.SDK_INT < 31) return true
        return context.getSystemService(AlarmManager::class.java).canScheduleExactAlarms()
    }

    /** The PendingIntent the alarm fires; the same requestCode always refers to the same alarm slot. */
    private fun alarmIntent(context: Context, requestCode: Int, title: String, body: String, weekly: Boolean): PendingIntent {
        val intent = Intent(context, AlarmReceiver::class.java).apply {
            putExtra(extraTitle, title)
            putExtra(extraBody, body)
            putExtra(extraWeekly, weekly)
        }
        return PendingIntent.getBroadcast(
            context, requestCode, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
    }

    /** Sets an alarm that still fires in Doze mode; exact if allowed, otherwise Android may delay it a little. */
    fun setAlarm(context: Context, triggerAtMillis: Long, requestCode: Int, title: String, body: String, weekly: Boolean) {
        val alarmManager = context.getSystemService(AlarmManager::class.java)
        val pending = alarmIntent(context, requestCode, title, body, weekly)
        if (canUseExactAlarms(context)) {
            alarmManager.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerAtMillis, pending)
        } else {
            alarmManager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerAtMillis, pending)
        }
    }

    /** Remembers the weekly schedule so it can be restored after reboot/update. */
    fun saveWeekly(context: Context, isoWeekday: Int, hour: Int, minute: Int, title: String, body: String) {
        context.getSharedPreferences(prefsName, Context.MODE_PRIVATE).edit()
            .putBoolean("enabled", true)
            .putInt("isoWeekday", isoWeekday)
            .putInt("hour", hour)
            .putInt("minute", minute)
            .putString("title", title)
            .putString("body", body)
            .apply()
    }

    /**
     * Schedules the next weekly alarm from the saved settings. Returns its time, or null if none is saved.
     * "Next" means after now AND after the alarm that last fired, so a reminder is never skipped
     * (e.g. set or rebooted at 06:59) and never repeated (e.g. the clock is set back after it fired). Review F17.
     */
    fun rescheduleWeeklyFromPrefs(context: Context): Long? {
        val prefs = context.getSharedPreferences(prefsName, Context.MODE_PRIVATE)
        if (!prefs.getBoolean("enabled", false)) return null
        val afterMillis = maxOf(System.currentTimeMillis(), prefs.getLong("lastFiredMillis", 0L))
        val next = nextWeeklyTrigger(prefs.getInt("isoWeekday", 5), prefs.getInt("hour", 7), prefs.getInt("minute", 0), afterMillis)
        setAlarm(
            context, next.timeInMillis, weeklyRequestCode,
            prefs.getString("title", "") ?: "", prefs.getString("body", "") ?: "", weekly = true,
        )
        prefs.edit().putLong("nextMillis", next.timeInMillis).apply()
        return next.timeInMillis
    }

    /** Cancels the weekly alarm and forgets its settings. */
    fun cancelWeekly(context: Context) {
        val alarmManager = context.getSystemService(AlarmManager::class.java)
        alarmManager.cancel(alarmIntent(context, weeklyRequestCode, "", "", true))
        context.getSharedPreferences(prefsName, Context.MODE_PRIVATE).edit().clear().apply()
    }

    /** Next planned weekly time, or null. */
    fun nextWeeklyMillis(context: Context): Long? {
        val prefs = context.getSharedPreferences(prefsName, Context.MODE_PRIVATE)
        return if (prefs.getBoolean("enabled", false)) prefs.getLong("nextMillis", 0L) else null
    }

    /** True if the app may post notifications (Android 13+ needs the user's permission). */
    fun notificationsAllowed(context: Context): Boolean {
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) return false
        return NotificationManagerCompat.from(context).areNotificationsEnabled()
    }

    /** Shows a notification now. Tapping it opens the app. Returns false if notifications aren't allowed. */
    fun showNotification(context: Context, title: String, body: String, notificationId: Int): Boolean {
        if (!notificationsAllowed(context)) return false
        if (Build.VERSION.SDK_INT >= 26) {
            val channel = NotificationChannel(channelId, "Weigh-in reminder", NotificationManager.IMPORTANCE_DEFAULT)
            context.getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
        val launchIntent = context.packageManager.getLaunchIntentForPackage(context.packageName)
        val contentIntent = PendingIntent.getActivity(
            context, 0, launchIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val notification = NotificationCompat.Builder(context, channelId)
            .setSmallIcon(context.applicationInfo.icon)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setContentIntent(contentIntent)
            .setAutoCancel(true)
            .build()
        return try {
            NotificationManagerCompat.from(context).notify(notificationId, notification)
            true
        } catch (e: SecurityException) { // permission revoked between the check and the call
            false
        }
    }
}
