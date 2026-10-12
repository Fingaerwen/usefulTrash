package io.github.fingaerwen.securestore

import android.os.Build
import android.os.Handler
import android.os.Looper
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyInfo
import android.security.keystore.KeyProperties
import io.flutter.embedding.engine.plugins.FlutterPlugin
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.security.GeneralSecurityException
import java.security.KeyStore
import java.security.ProviderException
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.GCMParameterSpec

/**
 * Encrypted storage for small secrets, such as the Supabase sign-in session (plan T1.1).
 *
 * - The AES-256 key is created inside Android Keystore (in the phone's security hardware) and can't be
 *   exported, so encrypted files are useless on any other phone or computer.
 * - Only the encrypted bytes are written, to the app's no-backup folder: Android leaves it out of
 *   cloud backups and phone-to-phone transfers.
 * - Each item is bound to its name (AES-GCM associated data), so files can't be swapped between names,
 *   and GCM detects any change to a file.
 * - An item that can't be decrypted (key lost, file from elsewhere, damaged) is deleted and reported as
 *   "unreadable"; the app then simply signs in again.
 * - Values are never logged. All work runs in order on one background thread, and every request gets
 *   exactly one reply on the main thread (Flet method calls have no default timeout).
 */
class SecureStorePlugin : FlutterPlugin, MethodChannel.MethodCallHandler {

    private lateinit var channel: MethodChannel
    private lateinit var storeDir: File
    private val worker: ExecutorService = Executors.newSingleThreadExecutor()
    private val mainThread = Handler(Looper.getMainLooper())

    private val keyAlias = "usefulTrashSecureStore"
    private val transformation = "AES/GCM/NoPadding"
    private val formatVersion: Byte = 1  // first byte of every item file, so the format can change later
    private val validName = Regex("^[A-Za-z0-9_-]{1,64}$")  // item names become file names: no paths allowed

    override fun onAttachedToEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        storeDir = File(binding.applicationContext.noBackupFilesDir, "secureStore")
        channel = MethodChannel(binding.binaryMessenger, "io.github.fingaerwen/secureStore") // same name as in Dart
        channel.setMethodCallHandler(this)
    }

    override fun onDetachedFromEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        channel.setMethodCallHandler(null)
        worker.shutdown()  // queued work still finishes
    }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        val reply = OneReply(result)
        val name = call.argument<String>("name").orEmpty()
        val value = call.argument<String>("value")
        runInBackground(reply) {
            when (call.method) {
                "save" -> save(name, value)
                "load" -> load(name)
                "delete" -> delete(name)
                "info" -> info()
                else -> failure("unknownMethod", "No method called ${call.method}")
            }
        }
    }

    /** Runs Keystore and file work off the main thread, then replies on the main thread. */
    private fun runInBackground(reply: OneReply, work: () -> Map<String, Any?>) {
        try {
            worker.execute {
                val answer = try {
                    work()
                } catch (e: Exception) {  // safety net: every request still gets an answer
                    failure(e.javaClass.simpleName, e.message)
                }
                mainThread.post { reply.send(answer) }
            }
        } catch (e: Exception) {  // e.g. the worker already shut down
            reply.send(failure(e.javaClass.simpleName, e.message))
        }
    }

    /** Encrypts value and saves it under name. Layout: version byte, IV length, IV, ciphertext + GCM tag. */
    private fun save(name: String, value: String?): Map<String, Any?> {
        if (value == null) return failure("missingValue", "No value was given")
        val file = itemFile(name)
        val cipher = Cipher.getInstance(transformation)
        cipher.init(Cipher.ENCRYPT_MODE, existingKey() ?: createKey())  // Keystore picks a fresh random IV
        cipher.updateAAD(name.toByteArray(Charsets.UTF_8))
        val encrypted = cipher.doFinal(value.toByteArray(Charsets.UTF_8))
        val iv = cipher.iv
        writeAtomically(file, byteArrayOf(formatVersion, iv.size.toByte()) + iv + encrypted)
        return mapOf("status" to "ok")
    }

    /** Reads and decrypts the item. Never creates a key: no key means nothing can be decrypted. */
    private fun load(name: String): Map<String, Any?> {
        val file = itemFile(name)
        if (!file.exists()) return mapOf("status" to "missing")
        return try {
            val blob = file.readBytes()
            require(blob.size > 2 && blob[0] == formatVersion) { "Unknown or damaged item format" }
            val ivSize = blob[1].toInt()
            require(ivSize in 12..16 && blob.size > 2 + ivSize) { "Damaged item" }
            val key = existingKey() ?: throw GeneralSecurityException("The key is missing (new phone, or app data restored)")
            val cipher = Cipher.getInstance(transformation)
            cipher.init(Cipher.DECRYPT_MODE, key, GCMParameterSpec(128, blob.copyOfRange(2, 2 + ivSize)))
            cipher.updateAAD(name.toByteArray(Charsets.UTF_8))
            val plain = cipher.doFinal(blob.copyOfRange(2 + ivSize, blob.size))
            mapOf("status" to "ok", "value" to String(plain, Charsets.UTF_8))
        } catch (e: GeneralSecurityException) {  // wrong/lost key, or the file was changed (GCM check failed)
            unreadable(file, e)
        } catch (e: IllegalArgumentException) {  // damaged file
            unreadable(file, e)
        }
    }

    /** Deletes an item that can never be decrypted again, and says why. */
    private fun unreadable(file: File, e: Exception): Map<String, Any?> {
        file.delete()
        return mapOf("status" to "unreadable", "message" to "${e.javaClass.simpleName}: ${e.message ?: ""}")
    }

    private fun delete(name: String): Map<String, Any?> {
        val file = itemFile(name)
        if (file.exists() && !file.delete()) return failure("deleteFailed", "Couldn't delete the item")
        return mapOf("status" to "ok")
    }

    /** Where the key lives (for checking on the phone) and how many items are stored. Never returns values. */
    @Suppress("DEPRECATION")  // isInsideSecureHardware: only used below Android 12
    private fun info(): Map<String, Any?> {
        val storedItems = storeDir.list()?.count { it.endsWith(".bin") } ?: 0
        val key = existingKey() ?: return mapOf("status" to "ok", "keyExists" to false, "storedItems" to storedItems)
        val keyInfo = SecretKeyFactory.getInstance(key.algorithm, "AndroidKeyStore")
            .getKeySpec(key, KeyInfo::class.java) as KeyInfo
        val keyLocation = if (Build.VERSION.SDK_INT >= 31) {
            when (keyInfo.securityLevel) {
                KeyProperties.SECURITY_LEVEL_STRONGBOX -> "StrongBox security chip"
                KeyProperties.SECURITY_LEVEL_TRUSTED_ENVIRONMENT -> "secure hardware (TEE)"
                KeyProperties.SECURITY_LEVEL_SOFTWARE -> "software only"
                else -> "secure hardware (unknown kind)"
            }
        } else if (keyInfo.isInsideSecureHardware) "secure hardware" else "software only"
        return mapOf("status" to "ok", "keyExists" to true, "keyLocation" to keyLocation, "storedItems" to storedItems)
    }

    /** The file for an item; refuses names that could point outside the store folder. */
    private fun itemFile(name: String): File {
        require(validName.matches(name)) { "Invalid item name" }
        return File(storeDir, "$name.bin")
    }

    /** Writes to a temporary file, forces it to disk, then renames it over the old one,
     *  so a crash or power loss leaves either the old item or the new one, never half of one. */
    private fun writeAtomically(file: File, bytes: ByteArray) {
        if (!storeDir.isDirectory && !storeDir.mkdirs()) throw IOException("Couldn't create the store folder")
        val temp = File(storeDir, "${file.name}.tmp")
        FileOutputStream(temp).use { out ->
            out.write(bytes)
            out.fd.sync()
        }
        if (!temp.renameTo(file)) {
            temp.delete()
            throw IOException("Couldn't replace ${file.name}")
        }
    }

    private fun existingKey(): SecretKey? {
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        return (keyStore.getEntry(keyAlias, null) as? KeyStore.SecretKeyEntry)?.secretKey
    }

    /** Creates the key in the StrongBox chip if the phone has one, otherwise in the normal secure hardware (TEE). */
    private fun createKey(): SecretKey {
        if (Build.VERSION.SDK_INT >= 28) {
            try {
                return generateKey(strongBox = true)
            } catch (e: ProviderException) {
                // No StrongBox chip (StrongBoxUnavailableException) or it refused: use the TEE instead.
            }
        }
        return generateKey(strongBox = false)
    }

    private fun generateKey(strongBox: Boolean): SecretKey {
        val spec = KeyGenParameterSpec.Builder(keyAlias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256)
            .setRandomizedEncryptionRequired(true)  // the Keystore chooses every IV, so one is never reused
            .apply { if (strongBox && Build.VERSION.SDK_INT >= 28) setIsStrongBoxBacked(true) }
            .build()
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").run {
            init(spec)
            generateKey()
        }
    }

    /** A failure reply in the shape Python expects. */
    private fun failure(errorType: String, message: String?): Map<String, Any?> =
        mapOf("status" to "error", "errorType" to errorType, "message" to (message ?: ""))

    /** Answers a Flutter request exactly once: a second answer would crash the app, none would hang Python. */
    private class OneReply(private val result: MethodChannel.Result) {
        private val answered = AtomicBoolean(false)

        fun send(value: Any?) {
            if (answered.compareAndSet(false, true)) result.success(value)
        }
    }
}
