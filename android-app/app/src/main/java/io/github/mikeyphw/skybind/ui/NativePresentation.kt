package io.github.mikeyphw.skybind.ui

import android.os.Build
import android.content.Context
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import io.github.mikeyphw.skybind.BuildConfig
import java.security.MessageDigest
import java.text.DateFormat
import java.util.Date
import java.util.Locale

/** All labels distinguish local observation from daemon-authoritative evidence. */
object NativePresentation {
    fun bytes(n: Long): String {
        if (n < 0) return "Unknown size"
        val suffix = arrayOf("B", "KiB", "MiB", "GiB", "TiB")
        var value = n.toDouble()
        var unit = 0
        while (value >= 1024 && unit < suffix.lastIndex) { value /= 1024; unit++ }
        return if (unit == 0) "$n B" else "${"%.1f".format(Locale.US, value)} ${suffix[unit]}"
    }
    fun time(raw: String): String {
        val millis = raw.toLongOrNull() ?: return "Time unavailable"
        if (millis < 946684800000L || millis > 4102444800000L) return "Time unavailable"
        return try { DateFormat.getDateTimeInstance(DateFormat.MEDIUM, DateFormat.SHORT).format(Date(millis)) }
        catch (_: IllegalArgumentException) { "Time unavailable" }
    }
    fun label(raw: String): String {
        val bounded = raw.take(90)
        return bounded.replace('.', ' ').replace('_', ' ').replace('-', ' ')
            .trim().split(Regex("\\s+")).filter { it.isNotEmpty() }
            .joinToString(" ") { it.replaceFirstChar { ch -> ch.titlecase(Locale.getDefault()) } }
            .take(90).ifBlank { "Unknown event" }
    }
    fun androidNetwork(context: Context): String = try {
        val manager = context.getSystemService(ConnectivityManager::class.java)
        val capabilities = manager?.let { it.getNetworkCapabilities(it.activeNetwork) }
        when {
            capabilities == null -> "No observed Android network"
            capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED) -> "Android network validated"
            else -> "Android network connected; internet unverified"
        }
    } catch (_: SecurityException) { "Android network permission unavailable" }
      catch (_: RuntimeException) { "Android network state unavailable" }

    fun notificationStatus(context: Context): String = try {
        val manager = context.getSystemService(android.app.NotificationManager::class.java)
        if (manager?.areNotificationsEnabled() == true) "Notifications enabled" else "Notifications disabled or restricted"
    } catch (_: RuntimeException) { "Notification visibility unknown" }

    fun signer(context: Context): String {
      return try {
        if (Build.VERSION.SDK_INT < 28) return "Not available on this Android version"
        @Suppress("DEPRECATION")
        val signing = context.packageManager.getPackageInfo(context.packageName,
            PackageManager.GET_SIGNING_CERTIFICATES).signingInfo
        val certs = signing?.apkContentsSigners ?: return "Unavailable"
        if (certs.size != 1) return "Ambiguous signing identity"
        MessageDigest.getInstance("SHA-256").digest(certs.single().toByteArray())
            .joinToString("") { "%02x".format(it.toInt() and 255) }
    } catch (_: Exception) { "Signing identity unavailable" }
    }

    fun version() = "${BuildConfig.VERSION_NAME} · code ${BuildConfig.VERSION_CODE}"
}
