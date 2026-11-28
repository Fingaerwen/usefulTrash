package io.github.fingaerwen.healthconnect

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.os.Bundle

/**
 * What Health Connect opens when you ask why Talon wants your steps and calories: the site's privacy page, which
 * says what Talon reads and that it stays in your own cloud and backups (plan HC1.1). Opens the browser and closes.
 */
class HealthPrivacyActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        try {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(privacyPage)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        } catch (_: ActivityNotFoundException) {
            // No browser on the phone: there's nothing more to show here.
        }
        finish()
    }

    companion object {
        const val privacyPage = "https://fingaerwen.github.io/usefulTrash/privacy.html#health-connect"
    }
}
