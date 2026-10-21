package io.github.mikeyphw.skybind.bridge

import android.content.Context
import android.content.pm.PackageManager
import android.net.LocalSocket
import android.net.LocalSocketAddress
import android.os.Build
import android.os.Process
import android.util.Base64
import org.json.JSONObject
import java.io.BufferedReader
import java.io.BufferedWriter
import java.io.InputStreamReader
import java.io.OutputStreamWriter

/**
 * App-process Android PackageManager authority for Skybind R1.
 *
 * This is NOT a BKX endpoint or a grant issuer. The privileged Go bridge
 * accepts only a kernel-credential-pinned Skybind app UID, PID incarnation
 * and SELinux label. It challenges every lookup and validates the DER signer
 * against the independent operator policy. The Android agent never accepts
 * a caller-provided certificate pin or filesystem/socket destination.
 *
 * Runs only while the user has opened the Skybind app, if an operator has
 * explicitly started the corresponding root listener. No daemon auto-start.
 */
object R1PMBridgeAgent {
    private const val SOCKET = "skybind-r1-pm-authority-v1"
    private const val MAX_LINE = 4096
    private val lock = Any()
    private var active: LocalSocket? = null
    private var starting = false

    fun start(context: Context) {
        synchronized(lock) {
            if (active != null || starting) return
            starting = true
        }
        val app = context.applicationContext
        Thread({
            try { runAgent(app) }
            catch (_: Exception) { /* no listener, denied peer, or app closing: fail closed */ }
            finally { synchronized(lock) { active?.close(); active = null; starting = false } }
        }, "skybind-r1-pm-authority").apply { isDaemon = true }.start()
    }

    fun stop() {
        synchronized(lock) { active?.close(); active = null }
    }

    private fun runAgent(context: Context) {
        // Do not elevate: the app's own kernel UID is the bridge identity.
        if (Process.myUid() < 10000 || Build.VERSION.SDK_INT < 28) return
        LocalSocket().use { socket ->
            socket.connect(LocalSocketAddress(SOCKET, LocalSocketAddress.Namespace.ABSTRACT))
            socket.soTimeout = 5_000
            synchronized(lock) { active = socket }
            val input = BufferedReader(InputStreamReader(socket.inputStream, Charsets.UTF_8))
            val output = BufferedWriter(OutputStreamWriter(socket.outputStream, Charsets.UTF_8))
            while (true) {
                val raw = input.readLine() ?: break
                if (raw.length > MAX_LINE) break
                val response = answer(context, raw)
                output.write(response)
                output.newLine()
                output.flush()
            }
        }
    }

    // Kept internal so instrumentation tests can exercise malformed/cross-app
    // requests without opening a privileged socket or granting access.
    internal fun answer(context: Context, raw: String): String {
        var nonce = ""
        var uid = 0
        var pkg = ""
        try {
            if (raw.length > MAX_LINE) throw SecurityException("oversized")
            val request = JSONObject(raw)
            if (request.length() != 4 || !request.has("version") || !request.has("nonce") ||
                !request.has("uid") || !request.has("package")) throw SecurityException("schema")
            if (request.getInt("version") != 1) throw SecurityException("version")
            nonce = request.getString("nonce")
            uid = request.getInt("uid")
            pkg = request.getString("package")
            if (!Regex("[0-9a-f]{64}").matches(nonce) || uid < 10000 ||
                pkg != "com.mikeyphw.bkx.android") throw SecurityException("denied")
            val pm = context.packageManager
            val packages = pm.getPackagesForUid(uid)?.toList() ?: throw SecurityException("not installed")
            if (packages != listOf(pkg)) throw SecurityException("shared uid or mismatch")
            val info = pm.getApplicationInfo(pkg, 0)
            if (info.uid != uid) throw SecurityException("uid mismatch")
            val signing = pm.getPackageInfo(pkg, PackageManager.GET_SIGNING_CERTIFICATES).signingInfo
                ?: throw SecurityException("missing signing info")
            val contents = signing.apkContentsSigners
            if (contents.size != 1) throw SecurityException("multi signer")
            val der = contents.single().toByteArray()
            if (der.size !in 64..8192) throw SecurityException("certificate size")
            return JSONObject().put("version", 1).put("nonce", nonce)
                .put("uid", uid).put("package", pkg)
                .put("record", JSONObject()
                    .put("uid", uid).put("packages_for_uid", org.json.JSONArray(packages))
                    .put("installed_package", pkg)
                    .put("signers_der_base64", org.json.JSONArray().put(Base64.encodeToString(der, Base64.NO_WRAP)))
                    .put("installed_for_user", true))
                .toString()
        } catch (_: Exception) {
            // Never echo supplied arbitrary strings or sensitive API errors.
            return JSONObject().put("version", 1).put("nonce", nonce)
                .put("uid", uid).put("package", pkg)
                .put("error", "not_authorized").toString()
        }
    }
}
