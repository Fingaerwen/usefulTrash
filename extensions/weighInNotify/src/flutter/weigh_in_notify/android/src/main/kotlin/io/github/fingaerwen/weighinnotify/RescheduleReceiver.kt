package io.github.fingaerwen.weighinnotify

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** Android forgets alarms on reboot and app update, and clock changes shift them: re-create both reminders. */
class RescheduleReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        WeighInScheduler.rescheduleWeeklyFromPrefs(context)
        WeighInScheduler.rescheduleDailyFromPrefs(context)
    }
}
