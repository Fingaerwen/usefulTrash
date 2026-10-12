package io.github.fingaerwen.nativegooglesignin

import android.app.Activity
import android.content.Context
import android.os.CancellationSignal
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
import com.google.android.libraries.identity.googleid.GetSignInWithGoogleOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import com.google.android.libraries.identity.googleid.GoogleIdTokenParsingException
import io.flutter.embedding.engine.plugins.FlutterPlugin
import io.flutter.embedding.engine.plugins.activity.ActivityAware
import io.flutter.embedding.engine.plugins.activity.ActivityPluginBinding
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Bridge between the Dart side (native_google_sign_in_service.dart) and Android's Credential Manager.
 *
 * Rules (plan AU1c + F9):
 * - Every request gets exactly one reply, including "cancelled" and every error. Flet method calls
 *   have no default timeout, so a missing reply would leave the sign-in button waiting forever.
 * - The Google ID token is only handed back to Python. It is never logged or saved here.
 * - No client secret: Google issues the token for the public Web client ID, and the Android
 *   client (package name + signing fingerprint, set up in Google Cloud) proves it's really this app.
 */
class NativeGoogleSignInPlugin : FlutterPlugin, MethodChannel.MethodCallHandler, ActivityAware {

    private lateinit var channel: MethodChannel
    private lateinit var appContext: Context
    private var activity: Activity? = null  // the current screen; Google's account picker needs one

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

    /** A failure reply in the shape Python expects. */
    private fun failure(errorType: String, message: String?): Map<String, Any?> =
        mapOf("status" to "error", "errorType" to errorType, "message" to (message ?: ""))

    // Keep track of the current screen (needed to show Google's account picker).
    override fun onAttachedToActivity(binding: ActivityPluginBinding) {
        activity = binding.activity
    }

    override fun onDetachedFromActivityForConfigChanges() {
        activity = null
    }

    override fun onReattachedToActivityForConfigChanges(binding: ActivityPluginBinding) {
        activity = binding.activity
    }

    override fun onDetachedFromActivity() {
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
