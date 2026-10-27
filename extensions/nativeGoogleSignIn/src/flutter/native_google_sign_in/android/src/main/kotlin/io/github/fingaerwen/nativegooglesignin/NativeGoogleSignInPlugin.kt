package io.github.fingaerwen.nativegooglesignin

import android.accounts.Account
import android.app.Activity
import android.content.Context
import android.content.Intent
import android.os.CancellationSignal
import android.os.SystemClock
import androidx.core.content.ContextCompat
import androidx.credentials.ClearCredentialStateRequest
import androidx.credentials.CredentialManager
import androidx.credentials.CredentialManagerCallback
import androidx.credentials.CustomCredential
import androidx.credentials.GetCredentialRequest
import androidx.credentials.GetCredentialResponse
import androidx.credentials.exceptions.ClearCredentialException
import androidx.credentials.exceptions.GetCredentialCancellationException
import androidx.credentials.exceptions.GetCredentialException
import androidx.credentials.exceptions.NoCredentialException
import com.google.android.gms.auth.api.identity.AuthorizationRequest
import com.google.android.gms.auth.api.identity.AuthorizationResult
import com.google.android.gms.auth.api.identity.ClearTokenRequest
import com.google.android.gms.auth.api.identity.Identity
import com.google.android.gms.common.api.ApiException
import com.google.android.gms.common.api.CommonStatusCodes
import com.google.android.gms.common.api.Scope
import com.google.android.libraries.identity.googleid.GetSignInWithGoogleOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import com.google.android.libraries.identity.googleid.GoogleIdTokenParsingException
import io.flutter.embedding.engine.plugins.FlutterPlugin
import io.flutter.embedding.engine.plugins.activity.ActivityAware
import io.flutter.embedding.engine.plugins.activity.ActivityPluginBinding
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import io.flutter.plugin.common.PluginRegistry
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Bridge between the Dart side (native_google_sign_in_service.dart) and Android's Credential Manager
 * (sign-in, check 2) and Google Play services' authorization API (Drive permission, check 7).
 *
 * Rules (plan AU1c + F9):
 * - Every request gets exactly one reply, including "cancelled" and every error. Flet method calls
 *   have no default timeout, so a missing reply would leave the sign-in button waiting forever.
 * - The Google ID token and Drive access tokens are only handed back to Python. They are never logged or saved here.
 * - No client secret: Google issues the token for the public Web client ID, and the Android
 *   client (package name + signing fingerprint, set up in Google Cloud) proves it's really this app.
 */
class NativeGoogleSignInPlugin : FlutterPlugin, MethodChannel.MethodCallHandler, ActivityAware,
    PluginRegistry.ActivityResultListener {

    private lateinit var channel: MethodChannel
    private lateinit var appContext: Context
    private var activity: Activity? = null  // the current screen. Google's account picker needs one
    private var activityBinding: ActivityPluginBinding? = null  // delivers the Drive consent screen's result
    private var pendingDriveConsent: OneReply? = null  // the request waiting for Google's Drive consent screen
    private var pendingDriveConsentSince = 0L  // when that screen was opened (SystemClock.elapsedRealtime)

    override fun onAttachedToEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        appContext = binding.applicationContext
        channel = MethodChannel(binding.binaryMessenger, "io.github.fingaerwen/nativeGoogleSignIn") // same name as in Dart
        channel.setMethodCallHandler(this)
    }

    override fun onDetachedFromEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        channel.setMethodCallHandler(null)
    }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        val reply = OneReply(result)
        try {
            when (call.method) {
                "getIdToken" -> getIdToken(
                    call.argument<String>("serverClientId").orEmpty(),
                    call.argument<String>("hashedNonce").orEmpty(),
                    reply,
                )
                "clearSignInState" -> clearSignInState(reply)
                "getDriveAccess" -> getDriveAccess(
                    call.argument<Boolean>("interactive") ?: false,
                    call.argument<String>("accountEmail").orEmpty(),
                    reply,
                )
                "clearDriveToken" -> clearDriveToken(call.argument<String>("accessToken").orEmpty(), reply)
                else -> reply.send(failure("unknownMethod", "No method called ${call.method}"))
            }
        } catch (e: Exception) {
            // Safety net: anything unexpected still gets an answer, so Python never waits forever.
            reply.send(failure(e.javaClass.simpleName, e.message))
        }
    }

    /** Shows Google's account picker ("Sign in with Google" button flow) and replies with the ID token. */
    private fun getIdToken(serverClientId: String, hashedNonce: String, reply: OneReply) {
        val currentActivity = activity
        if (currentActivity == null) {
            reply.send(failure("noScreen", "No app screen to show Google's account picker on"))
            return
        }
        if (serverClientId.isBlank()) {
            reply.send(failure("missingClientId", "No Google Web client ID was given"))
            return
        }
        if (hashedNonce.isBlank()) {
            reply.send(failure("missingNonce", "No nonce was given (it's required: replay protection)"))
            return
        }

        // The button flow shows every Google account on the phone and lets you add one.
        // The nonce goes into the ID token, so Supabase can check that the token was made for this sign-in.
        val signInOption = GetSignInWithGoogleOption.Builder(serverClientId)
            .setNonce(hashedNonce)
            .build()
        val request = GetCredentialRequest.Builder()
            .addCredentialOption(signInOption)
            .build()

        CredentialManager.create(currentActivity).getCredentialAsync(
            currentActivity,
            request,
            CancellationSignal(),
            ContextCompat.getMainExecutor(currentActivity),  // replies must happen on the main thread
            object : CredentialManagerCallback<GetCredentialResponse, GetCredentialException> {
                override fun onResult(result: GetCredentialResponse) = reply.send(readIdToken(result))
                override fun onError(e: GetCredentialException) = reply.send(describeError(e))
            },
        )
    }

    /** Pulls the Google ID token out of Credential Manager's answer. */
    private fun readIdToken(response: GetCredentialResponse): Map<String, Any?> {
        val credential = response.credential
        if (credential !is CustomCredential || credential.type != GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL) {
            return failure("unexpectedCredential", "Expected a Google ID token, got: ${credential.type}")
        }
        return try {
            mapOf("status" to "ok", "idToken" to GoogleIdTokenCredential.createFrom(credential.data).idToken)
        } catch (e: GoogleIdTokenParsingException) {
            failure("unreadableToken", "Google's answer couldn't be read (the sign-in library may need an update)")
        }
    }

    /** Turns a Credential Manager error into a reply. Errors never contain the token (there is none yet). */
    private fun describeError(e: GetCredentialException): Map<String, Any?> = when (e) {
        is GetCredentialCancellationException -> mapOf("status" to "cancelled")
        is NoCredentialException -> mapOf("status" to "noAccount", "message" to (e.errorMessage?.toString() ?: ""))
        else -> failure(e.type, e.errorMessage?.toString())  // e.g. a Google Cloud setup mismatch, with Google's error code
    }

    /** Forgets the chosen account, so the next sign-in shows the account picker again (needed to test a second account). */
    private fun clearSignInState(reply: OneReply) {
        CredentialManager.create(appContext).clearCredentialStateAsync(
            ClearCredentialStateRequest(),
            CancellationSignal(),
            ContextCompat.getMainExecutor(appContext),
            object : CredentialManagerCallback<Void?, ClearCredentialException> {
                override fun onResult(result: Void?) = reply.send(mapOf("status" to "ok"))
                override fun onError(e: ClearCredentialException) = reply.send(failure(e.type, e.errorMessage?.toString()))
            },
        )
    }

    /**
     * Asks Google Play services for a Drive access token (check 7, plan F14.1), limited to files this app creates.
     * No client secret and no refresh token in the app: Play services keeps the long-lived permission itself
     * and hands out access tokens that last about an hour. Asking again later returns a fresh one without
     * showing anything, as long as the permission wasn't removed.
     *
     * interactive = false: never shows a screen. Replies "needsConsent" if Google wants to ask first.
     * interactive = true: shows Google's consent screen when needed and replies once it closes.
     * accountEmail: the Google account the permission is for (the signed-in account). Empty = Google asks.
     */
    private fun getDriveAccess(interactive: Boolean, accountEmail: String, reply: OneReply) {
        val currentActivity = activity
        if (interactive && currentActivity == null) {
            reply.send(failure("noScreen", "No app screen to show Google's permission screen on"))
            return
        }
        val requestBuilder = AuthorizationRequest.builder().setRequestedScopes(listOf(Scope(driveFileScope)))
        if (accountEmail.isNotBlank()) requestBuilder.setAccount(Account(accountEmail, "com.google"))
        val client = if (currentActivity != null) {
            Identity.getAuthorizationClient(currentActivity)
        } else {
            Identity.getAuthorizationClient(appContext)
        }

        client.authorize(requestBuilder.build())  // listeners run on the main thread
            .addOnSuccessListener { result ->
                if (!result.hasResolution()) {
                    reply.send(readDriveAccess(result))  // already allowed: the token came back without any screen
                } else if (!interactive) {
                    reply.send(mapOf("status" to "needsConsent"))
                } else {
                    showDriveConsent(result, reply)
                }
            }
            .addOnFailureListener { e -> reply.send(describeAuthorizationError(e)) }
    }

    /** Opens Google's consent screen. Its result arrives in onActivityResult. */
    private fun showDriveConsent(result: AuthorizationResult, reply: OneReply) {
        val screen = activity
        val consentScreen = result.pendingIntent
        if (screen == null || consentScreen == null) {
            reply.send(failure("noScreen", "No app screen to show Google's permission screen on"))
            return
        }
        val earlierRequest = pendingDriveConsent
        if (earlierRequest != null) {
            if (SystemClock.elapsedRealtime() - pendingDriveConsentSince < staleConsentMs) {
                reply.send(failure("busy", "Google's permission screen is already open"))
                return
            }
            // The earlier screen never answered and Python stopped waiting for it: this request takes its place,
            // so a lost answer can't block the button until the app restarts.
            earlierRequest.send(failure("superseded", "A newer permission request replaced this one"))
        }
        pendingDriveConsent = reply
        pendingDriveConsentSince = SystemClock.elapsedRealtime()
        try {
            screen.startIntentSenderForResult(consentScreen.intentSender, driveConsentRequestCode, null, 0, 0, 0)
        } catch (e: Exception) {  // e.g. the screen couldn't be started
            pendingDriveConsent = null
            reply.send(failure(e.javaClass.simpleName, e.message))
        }
    }

    /** Receives the closed consent screen's answer (registered through the activity binding). */
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?): Boolean {
        if (requestCode != driveConsentRequestCode) return false  // someone else's result
        val reply = pendingDriveConsent ?: return true  // nobody waiting any more (already answered)
        pendingDriveConsent = null
        if (data == null) {
            reply.send(
                if (resultCode == Activity.RESULT_CANCELED) mapOf("status" to "cancelled")
                else failure("noResult", "Google's permission screen closed without an answer")
            )
            return true
        }
        try {
            reply.send(readDriveAccess(Identity.getAuthorizationClient(appContext).getAuthorizationResultFromIntent(data)))
        } catch (e: Exception) {
            reply.send(describeAuthorizationError(e))
        }
        return true
    }

    /** Pulls the access token out of Google's answer and checks the Drive permission is really in it. */
    private fun readDriveAccess(result: AuthorizationResult): Map<String, Any?> {
        val accessToken = result.accessToken
        val grantedScopes: List<String> = result.grantedScopes ?: emptyList()
        if (accessToken.isNullOrEmpty()) return failure("noToken", "Google returned no access token")
        if (grantedScopes.isNotEmpty() && driveFileScope !in grantedScopes) {
            return failure("notGranted", "The Drive permission wasn't granted")
        }
        return mapOf("status" to "ok", "accessToken" to accessToken, "grantedScopes" to grantedScopes)
    }

    /**
     * Removes an access token Google refused from Play services' cache, so the next getDriveAccess gets a new
     * one instead of the same refused token. The permission itself stays.
     */
    private fun clearDriveToken(accessToken: String, reply: OneReply) {
        if (accessToken.isBlank()) {
            reply.send(failure("missingToken", "No token was given"))
            return
        }
        Identity.getAuthorizationClient(appContext)
            .clearToken(ClearTokenRequest.builder().setToken(accessToken).build())
            .addOnSuccessListener { reply.send(mapOf("status" to "ok")) }
            .addOnFailureListener { e -> reply.send(describeAuthorizationError(e)) }
    }

    /** Turns a Play services error into a reply. "Cancelled" = closed by the user. Messages never contain tokens. */
    private fun describeAuthorizationError(e: Exception): Map<String, Any?> = when {
        e is ApiException && e.statusCode == CommonStatusCodes.CANCELED -> mapOf("status" to "cancelled")
        e is ApiException -> failure(CommonStatusCodes.getStatusCodeString(e.statusCode), e.message)
        else -> failure(e.javaClass.simpleName, e.message)
    }

    /** A failure reply in the shape Python expects. */
    private fun failure(errorType: String, message: String?): Map<String, Any?> =
        mapOf("status" to "error", "errorType" to errorType, "message" to (message ?: ""))

    // Keep track of the current screen (needed to show Google's account picker and permission screen).
    override fun onAttachedToActivity(binding: ActivityPluginBinding) = attachTo(binding)

    override fun onDetachedFromActivityForConfigChanges() = detachFromActivity()

    override fun onReattachedToActivityForConfigChanges(binding: ActivityPluginBinding) = attachTo(binding)

    override fun onDetachedFromActivity() {
        detachFromActivity()
        // The screen is gone for good, so the consent screen's result can't reach us: answer instead of hanging.
        pendingDriveConsent?.send(failure("screenClosed", "The app screen closed before Google's answer arrived"))
        pendingDriveConsent = null
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

    private companion object {
        /** Drive permission limited to files this app creates (plan F14.1). Google rates it non-sensitive. */
        const val driveFileScope = "https://www.googleapis.com/auth/drive.file"

        /** Marks the consent screen's result among the screen's results. Must fit in 16 bits (FlutterFragmentActivity). */
        const val driveConsentRequestCode = 0x7D01

        /** After this long an unanswered consent screen counts as lost: a bit more than Python's 300-second wait. */
        const val staleConsentMs = 310_000L
    }
}
