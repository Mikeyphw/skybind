package io.github.mikeyphw.skybind.bridge

import android.content.Context
import android.net.LocalSocket
import android.net.LocalSocketAddress
import android.os.Build
import android.os.Process
import java.io.BufferedReader
import java.io.BufferedWriter
import java.io.InputStreamReader
import java.io.OutputStreamWriter

/** Separate, fail-closed API-04 PackageManager authority. Reuses the same
 * reviewed PM query implementation as R1; no BKX app speaks this protocol.
 * Only a visible Skybind UI or user-enabled foreground service may start it.
 */
object API04PMBridgeAgent {
    private const val SOCKET = "skybind-api04-pm-authority-v1"
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
            try { runAgent(app) } catch (_: Exception) { /* denied or unavailable */ }
            finally { synchronized(lock) { active?.close(); active = null; starting = false } }
        }, "skybind-api04-pm-authority").apply { isDaemon = true }.start()
    }

    fun stop() { synchronized(lock) { active?.close(); active = null } }

    private fun runAgent(context: Context) {
        if (Process.myUid() < 10000 || Build.VERSION.SDK_INT < 28) return
        LocalSocket().use { socket ->
            socket.connect(LocalSocketAddress(SOCKET, LocalSocketAddress.Namespace.ABSTRACT))
            socket.soTimeout = 0
            synchronized(lock) { active = socket }
            val input = BufferedReader(InputStreamReader(socket.inputStream, Charsets.UTF_8))
            val output = BufferedWriter(OutputStreamWriter(socket.outputStream, Charsets.UTF_8))
            while (true) {
                val line = input.readLine() ?: break
                if (line.length > 4096) break
                output.write(R1PMBridgeAgent.answer(context, line))
                output.newLine()
                output.flush()
            }
        }
    }
}
