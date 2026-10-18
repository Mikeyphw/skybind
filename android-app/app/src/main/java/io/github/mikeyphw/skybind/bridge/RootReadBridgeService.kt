package io.github.mikeyphw.skybind.bridge

import android.content.Intent
import android.content.pm.PackageManager
import android.net.LocalSocket
import android.net.LocalSocketAddress
import android.os.Build
import android.os.Binder
import android.os.IBinder
import android.os.Process
import android.system.Os
import android.system.OsConstants
import com.topjohnwu.superuser.ipc.RootService
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.util.UUID

/**
 * App-owned privileged RootService, NOT an exported broker or an unrestricted root shell.
 * The only privileged operation is an allowlisted QUERY to Skybind's already running daemon.
 * Binding requires the root manager's explicit app grant. Not a BKX/chrootctl authorization path.
 */
class RootReadBridgeService : RootService() {
    private val calls = object : IRootReadBridge.Stub() {
        override fun query(operation: String?, arguments: String?): String {
            requireOwner()
            if (Process.myUid() != 0) throw SecurityException("root service unavailable")
            val args = checkedArguments(operation, arguments)
            return performRead(operation!!, args)
        }
    }

    override fun onBind(intent: Intent): IBinder = calls

    private fun requireOwner() {
        val caller = Binder.getCallingUid()
        if (caller <= 0 || caller == Process.myUid()) throw SecurityException("invalid app caller")
        val own = packageName
        val pm = packageManager
        val info = pm.getApplicationInfo(own, 0)
        if (caller != info.uid || pm.getPackagesForUid(caller)?.toList() != listOf(own)) {
            throw SecurityException("caller UID/package mismatch")
        }
        if (Build.VERSION.SDK_INT < 28) throw SecurityException("signing attestation requires Android 9+")
        val signing = pm.getPackageInfo(own, PackageManager.GET_SIGNING_CERTIFICATES).signingInfo
        if (signing == null || signing.apkContentsSigners.isNullOrEmpty()) {
            throw SecurityException("installed signing identity missing")
        }
        // libsu loads this service from the SAME installed application, but the
        // caller's actual UID is read from Binder, not from a serialized claim.
    }

    private fun checkedArguments(op: String?, raw: String?): JSONObject {
        val allowed = setOf("system.capabilities", "runtime.status", "provider.remotes",
            "mount.list", "jobs.status", "operation.events", "provider.browse")
        if (op !in allowed || raw == null || raw.length > 1024) throw SecurityException("unknown read method")
        val input = JSONObject(raw)
        if (op == "provider.browse") {
            if (input.length() != 1 || !input.has("remote")) throw SecurityException("invalid browse arguments")
            val endpoint = input.optString("remote", "")
            val split = endpoint.indexOf(':')
            if (split < 1 || split > 64 || endpoint.length > 578) throw SecurityException("invalid remote path")
            val name = endpoint.substring(0, split)
            val path = endpoint.substring(split + 1)
            try {
                io.github.mikeyphw.skybind.model.BrowseAddress.endpoint(name, path)
            } catch (_: IllegalArgumentException) {
                throw SecurityException("unsafe remote path")
            }
            return JSONObject().put("remote", endpoint)
        }
        if (op != "operation.events") {
            if (input.length() != 0) throw SecurityException("unexpected read arguments")
            return JSONObject()
        }
        if (input.keys().asSequence().any { it !in setOf("cursor", "limit", "operation_id", "wait_ms") }) {
            throw SecurityException("unexpected event arguments")
        }
        val cursor = input.optLong("cursor", -1)
        val limit = input.optInt("limit", -1)
        if (cursor < 0 || limit !in 1..64 || input.optString("operation_id", "") != "" ||
            input.optInt("wait_ms", -1) != 0) throw SecurityException("invalid event range")
        return JSONObject().put("cursor", cursor).put("limit", limit).put("operation_id", "").put("wait_ms", 0)
    }

    private fun verifySocketLayout() {
        // Canonical root-owned layout. No path input or symlinks from app callers.
        for (path in listOf("/data/adb/skybind", "/data/adb/skybind/run")) {
            val st = Os.lstat(path)
            if (st.st_uid != 0 || (st.st_mode and OsConstants.S_IFMT) != OsConstants.S_IFDIR ||
                (st.st_mode and 0x1ff) != 448) throw SecurityException("unsafe Skybind socket directory")
        }
        val sock = Os.lstat(SOCKET)
        if (sock.st_uid != 0 || (sock.st_mode and OsConstants.S_IFMT) != OsConstants.S_IFSOCK ||
            (sock.st_mode and 0x1ff) != 384) throw SecurityException("unsafe Skybind daemon socket")
    }

    private fun performRead(op: String, args: JSONObject): String {
        verifySocketLayout()
        val id = UUID.randomUUID().toString()
        val payload = JSONObject().put("schema_version", 1).put("request_id", id)
            .put("operation", op).put("class", "query").put("arguments", args)
            .toString().toByteArray(Charsets.UTF_8)
        if (payload.size > 65536) throw SecurityException("oversized request")
        LocalSocket().use { socket ->
            socket.connect(LocalSocketAddress(SOCKET, LocalSocketAddress.Namespace.FILESYSTEM))
            socket.soTimeout = if (op == "provider.browse") 35_000 else 4000
            if (socket.peerCredentials.uid != 0) throw SecurityException("non-root daemon peer")
            socket.outputStream.write(payload)
            socket.outputStream.flush()
            socket.shutdownOutput()
            val out = ByteArrayOutputStream()
            val chunk = ByteArray(8192)
            while (true) {
                val n = socket.inputStream.read(chunk)
                if (n < 0) break
                if (out.size() + n > 262144) throw IOException("oversized daemon reply")
                out.write(chunk, 0, n)
            }
            val response = JSONObject(out.toString("UTF-8"))
            if (response.optInt("schema_version", -1) != 1 || response.optString("request_id") != id ||
                !response.has("ok") || response.opt("ok") !is Boolean) throw IOException("invalid daemon response")
            return response.toString()
        }
    }

    companion object {
        private const val SOCKET = "/data/adb/skybind/run/skybindd.sock"
    }
}
