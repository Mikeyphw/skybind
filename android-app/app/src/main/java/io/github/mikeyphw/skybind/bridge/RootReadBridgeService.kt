package io.github.mikeyphw.skybind.bridge

import android.content.Intent
import android.content.pm.PackageManager
import android.net.LocalSocket
import android.net.LocalSocketAddress
import android.os.Build
import android.os.Binder
import android.os.IBinder
import android.os.Process
import android.os.SystemClock
import android.system.Os
import android.system.OsConstants
import com.topjohnwu.superuser.ipc.RootService
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.util.UUID

/** No exported broker or shell. Only app-UID Binder calls with exact typed RPCs. */
class RootReadBridgeService : RootService() {
    private data class Ticket(val session: String, val name: String, val proof: String, val deadline: Long)
    private val gate = Any()
    private val tickets = mutableMapOf<String, Ticket>()
    // Ownership is attached to an authenticated app session, NOT every daemon job.
    private val ownedRuns = mutableMapOf<String, String>()
    private val liveSessions = mutableSetOf<String>()
    // Tombstones prevent in-flight previews from recreating authority after close.
    private val forgottenSessions = LinkedHashSet<String>()
    private val jobName = Regex("[A-Za-z][A-Za-z0-9_-]{0,62}")
    private val uuid = Regex("[0-9a-fA-F-]{36}")
    private val runId = Regex("[0-9a-f]{32}")

    private val calls = object : IRootReadBridge.Stub() {
        override fun query(operation: String?, arguments: String?): String {
            authenticatedCaller()
            val method = operation ?: throw SecurityException("missing read method")
            return rpc(method, "query", checkedReadArguments(method, arguments)).toString()
        }
        override fun previewJob(sessionId: String?, jobName: String?): String {
            authenticatedCaller()
            val session = checkedSession(sessionId)
            if (jobName == null || !this@RootReadBridgeService.jobName.matches(jobName))
                throw SecurityException("invalid configured job name")
            val result = requireResult(rpc("job.run.preview", "preview", JSONObject().put("name", jobName)))
            if (result.optString("name") != jobName) throw IOException("job preview mismatch")
            val kind = result.optString("kind")
            // Sync can delete destinations; it remains outside this M3 slice.
            if (kind !in setOf("check", "copy") || result.optBoolean("destructive", true))
                throw SecurityException("operation class requires separate authorization")
            val proof = result.optString("proof")
            val source = result.optString("source")
            val destination = result.optString("destination")
            if (proof.length !in 16..2048 || source.isBlank() || destination.isBlank() ||
                source.length > 768 || destination.length > 768) throw IOException("invalid daemon preview")
            val ticket = UUID.randomUUID().toString()
            synchronized(gate) {
                val now = SystemClock.elapsedRealtime()
                tickets.entries.removeAll { it.value.deadline <= now }
                if (tickets.size >= 16) throw SecurityException("too many outstanding job previews")
                if (session in forgottenSessions) throw SecurityException("app session already closed")
                if (session !in liveSessions && liveSessions.size >= 32)
                    throw SecurityException("too many live app sessions")
                liveSessions.add(session)
                tickets[ticket] = Ticket(session, jobName, proof, now + 90_000L)
            }
            // Never return the daemon's reusable proof to the UI process.
            return JSONObject().put("id", ticket).put("name", jobName).put("kind", kind)
                .put("source", source).put("destination", destination).toString()
        }
        override fun startPreparedJob(sessionId: String?, previewId: String?): String {
            authenticatedCaller()
            val session = checkedSession(sessionId)
            if (previewId == null || !uuid.matches(previewId)) throw SecurityException("invalid preview ID")
            val ticket = synchronized(gate) { tickets.remove(previewId) }
                ?: throw SecurityException("preview absent or already consumed")
            if (ticket.session != session || ticket.deadline <= SystemClock.elapsedRealtime())
                throw SecurityException("expired or foreign preview")
            // The daemon atomically consumes the action/name/revision/digest-bound proof.
            // Transport ambiguity MUST NOT cause an automatic retry.
            val result = requireResult(rpc("job.run", "run", JSONObject()
                .put("name", ticket.name).put("proof", ticket.proof)))
            val id = result.optString("id")
            if (!runId.matches(id) || result.optString("name") != ticket.name ||
                result.optString("state") != "RUNNING") throw IOException("job claim outcome unverified")
            synchronized(gate) {
                // A disconnect may have raced the daemon claim. Never recreate
                // cancellation authority for an already forgotten app session.
                if (session !in liveSessions)
                    throw IOException("session ended after job claim; inspect authoritative Jobs")
                ownedRuns[id] = session
            }
            return JSONObject().put("id", id).put("name", ticket.name).put("state", "RUNNING").toString()
        }
        override fun cancelOwnedRun(sessionId: String?, runId: String?): String {
            authenticatedCaller()
            val session = checkedSession(sessionId)
            if (runId == null || !this@RootReadBridgeService.runId.matches(runId))
                throw SecurityException("invalid run ID")
            synchronized(gate) {
                if (ownedRuns[runId] != session) throw SecurityException("job not owned by this session")
            }
            val result = requireResult(rpc("operation.cancel", "cancel", JSONObject().put("id", runId)))
            if (result.optString("id") != runId) throw IOException("cancel result identity mismatch")
            synchronized(gate) { ownedRuns.remove(runId, session) }
            return JSONObject().put("id", runId).put("state", result.optString("state")).toString()
        }
        override fun forgetSession(sessionId: String?) {
            authenticatedCaller()
            val session = checkedSession(sessionId)
            synchronized(gate) {
                tickets.entries.removeAll { it.value.session == session }
                ownedRuns.entries.removeAll { it.value == session }
                liveSessions.remove(session)
                forgottenSessions.add(session)
                while (forgottenSessions.size > 64)
                    forgottenSessions.remove(forgottenSessions.first())
            }
        }
    }

    override fun onBind(intent: Intent): IBinder = calls

    private fun checkedSession(id: String?): String {
        if (id == null || !uuid.matches(id)) throw SecurityException("invalid app session")
        return id
    }

    private fun authenticatedCaller() {
        if (Process.myUid() != 0) throw SecurityException("root service unavailable")
        val caller = Binder.getCallingUid()
        if (caller <= 0 || caller == Process.myUid()) throw SecurityException("invalid app caller")
        val own = packageName
        val pm = packageManager
        val info = pm.getApplicationInfo(own, 0)
        if (caller != info.uid || pm.getPackagesForUid(caller)?.toList() != listOf(own))
            throw SecurityException("caller UID/package mismatch")
        if (Build.VERSION.SDK_INT < 28) throw SecurityException("signing attestation requires Android 9+")
        val signing = pm.getPackageInfo(own, PackageManager.GET_SIGNING_CERTIFICATES).signingInfo
        if (signing == null || signing.apkContentsSigners.isNullOrEmpty())
            throw SecurityException("installed signing identity missing")
    }

    private fun checkedReadArguments(op: String?, raw: String?): JSONObject {
        val allowed = setOf("system.capabilities", "runtime.status", "provider.remotes",
            "mount.list", "jobs.status", "operation.events", "provider.browse")
        if (op !in allowed || raw == null || raw.length > 1024)
            throw SecurityException("unknown read method")
        val input = JSONObject(raw)
        if (op == "provider.browse") {
            if (input.length() != 1 || !input.has("remote")) throw SecurityException("invalid browse arguments")
            val endpoint = input.optString("remote", "")
            val split = endpoint.indexOf(':')
            if (split < 1 || split > 64 || endpoint.length > 578) throw SecurityException("invalid remote path")
            val name = endpoint.substring(0, split)
            val path = endpoint.substring(split + 1)
            try { io.github.mikeyphw.skybind.model.BrowseAddress.endpoint(name, path) }
            catch (_: IllegalArgumentException) { throw SecurityException("unsafe remote path") }
            return JSONObject().put("remote", endpoint)
        }
        if (op != "operation.events") {
            if (input.length() != 0) throw SecurityException("unexpected read arguments")
            return JSONObject()
        }
        if (input.keys().asSequence().any { it !in setOf("cursor", "limit", "operation_id", "wait_ms") })
            throw SecurityException("unexpected event arguments")
        val cursor = input.optLong("cursor", -1)
        val limit = input.optInt("limit", -1)
        if (cursor < 0 || limit !in 1..64 || input.optString("operation_id", "") != "" ||
            input.optInt("wait_ms", -1) != 0) throw SecurityException("invalid event range")
        return JSONObject().put("cursor", cursor).put("limit", limit)
            .put("operation_id", "").put("wait_ms", 0)
    }

    private fun verifySocketLayout() {
        for (path in listOf("/data/adb/skybind", "/data/adb/skybind/run")) {
            val st = Os.lstat(path)
            if (st.st_uid != 0 || (st.st_mode and OsConstants.S_IFMT) != OsConstants.S_IFDIR ||
                (st.st_mode and 0x1ff) != 448) throw SecurityException("unsafe Skybind socket directory")
        }
        val sock = Os.lstat(SOCKET)
        if (sock.st_uid != 0 || (sock.st_mode and OsConstants.S_IFMT) != OsConstants.S_IFSOCK ||
            (sock.st_mode and 0x1ff) != 384) throw SecurityException("unsafe Skybind daemon socket")
    }

    private fun requireResult(body: JSONObject): JSONObject {
        if (body.opt("ok") != true) throw IOException("daemon refused operation")
        return body.optJSONObject("result") ?: throw IOException("missing daemon result")
    }

    private fun rpc(op: String, type: String, args: JSONObject): JSONObject {
        verifySocketLayout()
        val id = UUID.randomUUID().toString()
        val payload = JSONObject().put("schema_version", 1).put("request_id", id)
            .put("operation", op).put("class", type).put("arguments", args)
            .toString().toByteArray(Charsets.UTF_8)
        if (payload.size > 65536) throw SecurityException("oversized request")
        LocalSocket().use { socket ->
            socket.connect(LocalSocketAddress(SOCKET, LocalSocketAddress.Namespace.FILESYSTEM))
            socket.soTimeout = if (op == "provider.browse") 35_000 else 8_000
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
                !response.has("ok") || response.opt("ok") !is Boolean)
                throw IOException("invalid daemon response")
            return response
        }
    }

    companion object { private const val SOCKET = "/data/adb/skybind/run/skybindd.sock" }
}
