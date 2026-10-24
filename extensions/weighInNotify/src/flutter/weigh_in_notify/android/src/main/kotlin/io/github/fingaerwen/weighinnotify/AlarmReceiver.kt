package io.github.fingaerwen.weighinnotify

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** Runs when an alarm goes off: shows the notification and, for a repeating one, schedules the next. */
class AlarmReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val title = intent.getStringExtra(WeighInScheduler.extraTitle) ?: ""
        val body = intent.getStringExtra(WeighInScheduler.extraBody) ?: ""
        when (intent.getStringExtra(WeighInScheduler.extraKind) ?: WeighInScheduler.kindOneOff) {
            WeighInScheduler.kindWeekly -> {
                WeighInScheduler.showNotification(context, title, body, WeighInScheduler.weeklyRequestCode)
                WeighInScheduler.markFired(context, WeighInScheduler.kindWeekly) // never fire one slot twice
                WeighInScheduler.rescheduleWeeklyFromPrefs(context)
            }
            WeighInScheduler.kindDaily -> {
                WeighInScheduler.showNotification(context, title, body, WeighInScheduler.dailyRequestCode,
                    WeighInScheduler.dailyChannelId, WeighInScheduler.dailyChannelName)
                WeighInScheduler.markFired(context, WeighInScheduler.kindDaily)
                WeighInScheduler.rescheduleDailyFromPrefs(context)
            }
            else -> WeighInScheduler.showNotification(context, title, body, WeighInScheduler.oneOffRequestCode)
        }
    }
}
