package com.mikeyphw.bkx.r1

import android.net.LocalSocket
import android.net.LocalSocketAddress
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.time.Instant

/** Optional source adapter for BKX integration, NOT part of the installed BKX APK.
 * Only invoke from an explicitly selected read-only provider path. Failure
 * MUST return an error to the caller, never silently retry a write via rclone.
 * The operator approves the exact BKX PID out-of-band; tokens are in RAM only.
 */
object SkybindR1ReadClient {
    private const val GRANTS = "skybind-r1-grant-handoff-v1"
    private const val READ = "skybind-r1-consumer-gateway-v1"
    private const val MAX_RESPONSE = 1024 * 1024
    private val operations = setOf("system.capabilities", "rclone.version", "rclone.listremotes", "rclone.lsjson", "rclone.size")

    private fun socket(address: String): LocalSocket = LocalSocket().apply {
        connect(LocalSocketAddress(address, LocalSocketAddress.Namespace.ABSTRACT))
        soTimeout = 5000
    }
    private fun boundedLine(socket: LocalSocket): String {
        val bytes = ByteArrayOutputStream()
        while (true) {
            val next = socket.inputStream.read()
            if (next == -1) error("R1 incomplete response")
            if (next == 10) break
            if (bytes.size() >= MAX_RESPONSE) error("R1 oversized response")
            bytes.write(next)
        }
        return bytes.toString(Charsets.UTF_8.name())
    }
    /** A grant is pushed only to the kernel-authenticated app process. */
    fun read(operation: String, remote: String, path: String = ""): Any {
        require(operation in operations) { "R1 read-only operation required" }
        require(Regex("[A-Za-z][A-Za-z0-9_-]{0,62}").matches(remote)) { "Invalid remote" }
        require(path.length <= 4096 && !path.startsWith("/") &&
            !path.any { it == '\\' || it == ':' || it == '%' || it == '?' || it == '#' || it == '\r' || it == '\n' || it == '\u0000' } &&
            (path.isEmpty() || path.split('/').all { it.isNotEmpty() && it != "." && it != ".." })) { "Invalid path" }
        val offer = socket(GRANTS).use { JSONObject(boundedLine(it)) }
        require(offer.length() == 3 && offer.getInt("version") == 1) { "Invalid grant" }
        val token = offer.getString("token")
        require(Regex("[0-9a-f]{64}").matches(token) && Instant.parse(offer.getString("expires_at")).isAfter(Instant.now())) { "Grant expired or invalid" }
        val request = JSONObject().put("version", 1).put("token", token)
            .put("operation", operation).put("remote", remote).put("path", path)
        // No token is stored in preferences, an Intent, logcat, or a file.
        return socket(READ).use { s ->
            s.outputStream.write(request.toString().toByteArray(Charsets.UTF_8))
            s.shutdownOutput()
            val response = JSONObject(boundedLine(s))
            require(response.getInt("version") == 1 && response.getBoolean("ok") && !response.has("error")) { "R1 read denied" }
            response.get("result")
        }
    }
}
