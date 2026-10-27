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

/**
 * All alarm + notification logic, shared by the plugin and the broadcast receivers.
 * Two repeating reminders, each in its own alarm slot: the weekly weigh-in and a daily one (the creatine
 * reminder, WD3.8). Each slot's settings are saved separately, so one never disturbs the other.
 * The rest timer's alert (RT1.1) has a slot of its own too: one-off, on the dot, in a channel that pops up.
 */
object WeighInScheduler {
    private const val channelId = "weighIn"
    private const val channelName = "Weigh-in reminder"
    const val dailyChannelId = "daily"
    const val dailyChannelName = "Daily reminder"
    private const val prefsName = "weighInNotify"
    private const val dailyPrefsName = "weighInNotifyDaily"
    const val weeklyRequestCode = 5001
    const val oneOffRequestCode = 5002
    const val showNowNotificationId = 5003
    const val dailyRequestCode = 5004
    const val restRequestCode = 5005
    const val restChannelId = "rest"
    const val restChannelName = "Rest timer"
    const val extraTitle = "title"
    const val extraBody = "body"
    const val extraKind = "kind"
    const val kindWeekly = "weekly"
    const val kindDaily = "daily"
    const val kindOneOff = "oneOff"
    const val kindRest = "rest"

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

    /** First moment at hour:minute that is strictly after [afterMillis] (local time, DST-safe). */
    fun nextDailyTrigger(hour: Int, minute: Int, afterMillis: Long): Calendar {
        val after = Calendar.getInstance().apply { timeInMillis = afterMillis }
        val target = (after.clone() as Calendar).apply {
            set(Calendar.HOUR_OF_DAY, hour)
            set(Calendar.MINUTE, minute)
            set(Calendar.SECOND, 0)
            set(Calendar.MILLISECOND, 0)
        }
        if (!target.after(after)) target.add(Calendar.DAY_OF_YEAR, 1)
        return target
    }

    private fun prefsFor(context: Context, kind: String) =
        context.getSharedPreferences(if (kind == kindDaily) dailyPrefsName else prefsName, Context.MODE_PRIVATE)

    /** Records that the alarm planned for "nextMillis" has just gone off (it must never fire twice). */
    fun markFired(context: Context, kind: String) {
        val prefs = prefsFor(context, kind)
        prefs.edit().putLong("lastFiredMillis", prefs.getLong("nextMillis", 0L)).apply()
    }

    /** Human-readable local time, e.g. "2026-10-09 07:00". */
    fun formatTime(millis: Long): String = SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.US).format(Date(millis))

    /** True if exact alarms are allowed (always true below Android 12). */
    fun canUseExactAlarms(context: Context): Boolean {
        if (Build.VERSION.SDK_INT < 31) return true
        return context.getSystemService(AlarmManager::class.java).canScheduleExactAlarms()
    }

    /** The PendingIntent the alarm fires. The same requestCode always refers to the same alarm slot. */
    private fun alarmIntent(context: Context, requestCode: Int, title: String, body: String, kind: String): PendingIntent {
        val intent = Intent(context, AlarmReceiver::class.java).apply {
            putExtra(extraTitle, title)
            putExtra(extraBody, body)
            putExtra(extraKind, kind)
        }
        return PendingIntent.getBroadcast(
            context, requestCode, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
    }

    /** Opens the app (used when a notification or the clock's "next alarm" entry is tapped). */
    private fun openAppIntent(context: Context): PendingIntent {
        val launchIntent = context.packageManager.getLaunchIntentForPackage(context.packageName)
        return PendingIntent.getActivity(
            context, 0, launchIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
    }

    /**
     * Sets an alarm that still fires in Doze mode.
     * Weekly and daily reminders and the rest timer: alarm-clock mode (review F21.2). OnePlus stretched normal
     * exact alarms into a 1-hour window even with battery "Unrestricted", while alarm-clock alarms (like the
     * Clock app's) stay on the dot. Side effect: Android shows an alarm icon and lists it as the next alarm.
     * Other alarms: exact if allowed, otherwise Android may delay them a little.
     */
    fun setAlarm(context: Context, triggerAtMillis: Long, requestCode: Int, title: String, body: String, kind: String) {
        val alarmManager = context.getSystemService(AlarmManager::class.java)
        val pending = alarmIntent(context, requestCode, title, body, kind)
        if (kind != kindOneOff && canUseExactAlarms(context)) {
            alarmManager.setAlarmClock(AlarmManager.AlarmClockInfo(triggerAtMillis, openAppIntent(context)), pending)
        } else if (canUseExactAlarms(context)) {
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
            prefs.getString("title", "") ?: "", prefs.getString("body", "") ?: "", kindWeekly,
        )
        prefs.edit().putLong("nextMillis", next.timeInMillis).apply()
        return next.timeInMillis
    }

    /** Cancels the weekly alarm and forgets its settings (the daily one keeps its own). */
    fun cancelWeekly(context: Context) {
        val alarmManager = context.getSystemService(AlarmManager::class.java)
        alarmManager.cancel(alarmIntent(context, weeklyRequestCode, "", "", kindWeekly))
        context.getSharedPreferences(prefsName, Context.MODE_PRIVATE).edit().clear().apply()
    }

    /** Cancels the rest timer's alarm and takes away its notification if it's showing (RT1.1). */
    fun cancelRest(context: Context) {
        val alarmManager = context.getSystemService(AlarmManager::class.java)
        alarmManager.cancel(alarmIntent(context, restRequestCode, "", "", kindRest))
        NotificationManagerCompat.from(context).cancel(restRequestCode)
    }

    /** Remembers the daily schedule so it can be restored after reboot/update. */
    fun saveDaily(context: Context, hour: Int, minute: Int, title: String, body: String) {
        prefsFor(context, kindDaily).edit()
            .putBoolean("enabled", true)
            .putInt("hour", hour)
            .putInt("minute", minute)
            .putString("title", title)
            .putString("body", body)
            .apply()
    }

    /** Schedules the next daily alarm from the saved settings, after now and after the one that last fired. */
    fun rescheduleDailyFromPrefs(context: Context): Long? {
        val prefs = prefsFor(context, kindDaily)
        if (!prefs.getBoolean("enabled", false)) return null
        val afterMillis = maxOf(System.currentTimeMillis(), prefs.getLong("lastFiredMillis", 0L))
        val next = nextDailyTrigger(prefs.getInt("hour", 8), prefs.getInt("minute", 0), afterMillis)
        setAlarm(
            context, next.timeInMillis, dailyRequestCode,
            prefs.getString("title", "") ?: "", prefs.getString("body", "") ?: "", kindDaily,
        )
        prefs.edit().putLong("nextMillis", next.timeInMillis).apply()
        return next.timeInMillis
    }

    /** Cancels the daily alarm and forgets its settings. */
    fun cancelDaily(context: Context) {
        val alarmManager = context.getSystemService(AlarmManager::class.java)
        alarmManager.cancel(alarmIntent(context, dailyRequestCode, "", "", kindDaily))
        prefsFor(context, kindDaily).edit().clear().apply()
    }

    /** Next planned daily time, or null. */
    fun nextDailyMillis(context: Context): Long? {
        val prefs = prefsFor(context, kindDaily)
        return if (prefs.getBoolean("enabled", false)) prefs.getLong("nextMillis", 0L) else null
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

    /**
     * Shows a notification now. Tapping it opens the app. Returns false if notifications aren't allowed.
     * Each reminder has its own channel, so either can be muted in Android's settings without the other.
     */
    fun showNotification(
        context: Context, title: String, body: String, notificationId: Int,
        channel: String = channelId, name: String = channelName, importance: Int = NotificationManager.IMPORTANCE_DEFAULT,
    ): Boolean {
        if (!notificationsAllowed(context)) return false
        if (Build.VERSION.SDK_INT >= 26) {
            val notificationChannel = NotificationChannel(channel, name, importance)
            context.getSystemService(NotificationManager::class.java).createNotificationChannel(notificationChannel)
        }
        val contentIntent = openAppIntent(context)
        val notification = NotificationCompat.Builder(context, channel)
            .setSmallIcon(R.drawable.weigh_in_notify_ic_stat) // single-colour shape. The full-colour app icon showed as a grey blob
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
