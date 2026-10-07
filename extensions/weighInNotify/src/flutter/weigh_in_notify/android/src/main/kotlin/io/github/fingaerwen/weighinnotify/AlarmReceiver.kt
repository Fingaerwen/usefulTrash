package io.github.fingaerwen.weighinnotify

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** Runs when an alarm goes off: shows the notification and, for the weekly one, schedules next week. */
class AlarmReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val title = intent.getStringExtra(WeighInScheduler.extraTitle) ?: ""
        val body = intent.getStringExtra(WeighInScheduler.extraBody) ?: ""
        val weekly = intent.getBooleanExtra(WeighInScheduler.extraWeekly, false)
        val notificationId = if (weekly) WeighInScheduler.weeklyRequestCode else WeighInScheduler.oneOffRequestCode
        WeighInScheduler.showNotification(context, title, body, notificationId)
        if (weekly) WeighInScheduler.rescheduleWeeklyFromPrefs(context)
    }
}
