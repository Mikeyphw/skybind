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
import org.json.JSONArray
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.util.UUID

/** No exported broker or shell. Only app-UID Binder calls with exact typed RPCs. */
class RootReadBridgeService : RootService() {
    private data class Ticket(val session: String, val name: String, val proof: String, val deadline: Long)
    private val gate = Any()
    private val tickets = mutableMapOf<String, Ticket>()
    private data class MountTicket(
        val session: String, val action: String, val name: String, val proof: String,
        val revision: Long, val observed: String, val desired: Boolean, val pid: Int,
        val deadline: Long,
    )
    private val mountTickets = mutableMapOf<String, MountTicket>()
    private data class ConfigTicket(val session: String, val action: String, val name: String,
        val candidate: String, val proof: String, val revision: Long, val deadline: Long)
    private val configTickets = mutableMapOf<String, ConfigTicket>()
    private data class RollbackTicket(val session: String, val proof: String,
        val revision: Long, val deadline: Long)
    private val rollbackTickets = mutableMapOf<String, RollbackTicket>()
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
        /** The app can request only four literal mount actions. No arbitrary RPC is forwarded. */
        override fun previewStartMount(sessionId: String?, mountName: String?): String =
            previewMountTicket(sessionId, "start", mountName)
        override fun previewStopMount(sessionId: String?, mountName: String?): String =
            previewMountTicket(sessionId, "stop", mountName)
        override fun previewRestartMount(sessionId: String?, mountName: String?): String =
            previewMountTicket(sessionId, "restart", mountName)
        override fun previewReconcileMount(sessionId: String?): String =
            previewMountTicket(sessionId, "reconcile", "")
        private fun previewMountTicket(sessionId: String?, action: String, mountName: String?): String {
            authenticatedCaller()
            val session = checkedSession(sessionId)
            val verb = action ?: throw SecurityException("missing mount action")
            if (verb !in setOf("start", "stop", "restart", "reconcile"))
                throw SecurityException("unsupported mount operation")
            val name = mountName ?: throw SecurityException("missing mount name")
            if ((verb == "reconcile" && name.isNotEmpty()) ||
                (verb != "reconcile" && !jobName.matches(name)))
                throw SecurityException("unsafe mount name")
            val registry = requireResult(rpc("config.snapshot", "query", JSONObject()))
            val revision = registry.optLong("revision", -1L)
            val entries = registry.optJSONArray("mounts") ?: throw IOException("missing mount registry")
            if (revision < 0 || entries.length() > 64) throw IOException("invalid mount registry")
            val names = mutableSetOf<String>()
            for (i in 0 until entries.length()) {
                val configured = entries.optJSONObject(i)?.optString("name") ?: throw IOException("invalid mount")
                if (!jobName.matches(configured) || !names.add(configured))
                    throw IOException("invalid mount registry name")
            }
            if (verb != "reconcile" && name !in names) throw SecurityException("unconfigured mount")
            val state = if (verb == "reconcile") null else checkedMountState(name)
            if (verb == "stop" && state!!.optString("observed") != "RUNNING")
                throw SecurityException("mount is not running")
            if (verb == "restart" && state!!.optString("observed") != "RUNNING")
                throw SecurityException("restart requires running mount")
            val plan = if (verb == "start")
                requireResult(rpc("mount.start.preview", "preview", JSONObject().put("name", name)))
                else null
            val proof = plan?.optString("proof", "") ?: ""
            if (verb == "start" && (proof.length !in 16..2048 ||
                    plan!!.optString("mount") != name ||
                    plan.optString("mountpoint").isBlank() ||
                    plan.optString("remote").isBlank())) throw IOException("invalid start preview")
            val id = UUID.randomUUID().toString()
            synchronized(gate) {
                val now = SystemClock.elapsedRealtime()
                mountTickets.entries.removeAll { it.value.deadline <= now || it.value.session == session }
                if (session in forgottenSessions) throw SecurityException("closed app session")
                if (session !in liveSessions && liveSessions.size >= 32)
                    throw SecurityException("too many live app sessions")
                if (mountTickets.size >= 16) throw SecurityException("too many mount previews")
                liveSessions.add(session)
                mountTickets[id] = MountTicket(session, verb, name, proof, revision,
                    state?.getString("observed") ?: "", state?.getBoolean("desired") ?: false,
                    state?.optInt("pid", 0) ?: 0, now + 60_000L)
            }
            // UI gets only the root-service ticket. The backend proof never leaves root.
            return JSONObject().put("id", id).put("action", verb).put("name", name)
                .put("observed", state?.getString("observed") ?: "")
                .put("desired", state?.getBoolean("desired") ?: false)
                .put("remote", plan?.optString("remote", "")?.take(768) ?: "")
                .put("mountpoint", plan?.optString("mountpoint", "")?.take(768) ?: "")
                .put("configured_count", entries.length()).toString()
        }
        override fun confirmMount(sessionId: String?, previewId: String?): String {
            authenticatedCaller()
            val session = checkedSession(sessionId)
            if (previewId == null || !uuid.matches(previewId))
                throw SecurityException("invalid mount ticket")
            // Consume before I/O. Never retry an ambiguous mount mutation.
            val mountTicket = synchronized(gate) { mountTickets.remove(previewId) }
                ?: throw SecurityException("mount ticket absent or consumed")
            if (mountTicket.session != session || mountTicket.deadline <= SystemClock.elapsedRealtime())
                throw SecurityException("foreign or expired mount preview")
            synchronized(gate) {
                if (session !in liveSessions || session in forgottenSessions)
                    throw SecurityException("session closed before mutation")
            }
            val registry = requireResult(rpc("config.snapshot", "query", JSONObject()))
            if (registry.optLong("revision", -1) != mountTicket.revision)
                throw SecurityException("mount config changed after preview")
            if (mountTicket.action != "reconcile") {
                val state = checkedMountState(mountTicket.name)
                if (state.getString("observed") != mountTicket.observed ||
                    state.getBoolean("desired") != mountTicket.desired ||
                    state.optInt("pid", 0) != mountTicket.pid)
                    throw SecurityException("mount status changed after preview")
            }
            val operation = "mount." + mountTicket.action
            val args = when (mountTicket.action) {
                "start" -> JSONObject().put("name", mountTicket.name).put("proof", mountTicket.proof)
                "stop", "restart" -> JSONObject().put("name", mountTicket.name)
                "reconcile" -> JSONObject()
                else -> throw SecurityException("invalid mount ticket action")
            }
            val envelope = rpc(operation, if (mountTicket.action == "reconcile") "reconcile" else "run", args)
            if (envelope.opt("ok") != true) throw IOException("daemon rejected mount action")
            val result = envelope.opt("result")
            if (mountTicket.action == "reconcile") {
                val health = result as? JSONArray ?: throw IOException("invalid reconcile result")
                if (health.length() > 64) throw IOException("oversized reconcile result")
            } else {
                val state = result as? JSONObject ?: throw IOException("invalid mount result")
                if (state.optString("name") != mountTicket.name ||
                    state.optString("observed") !in setOf("RUNNING", "STOPPED", "DEGRADED", "MOUNT_STALE") ||
                    state.opt("desired") !is Boolean) throw IOException("unverified mount result")
            }
            // An OK response is not a guarantee of durable mount health.
            return JSONObject().put("action", mountTicket.action).put("name", mountTicket.name)
                .put("accepted", true).put("refresh_required", true).toString()
        }
        override fun readMountConfiguration(sessionId: String?): String {
            authenticatedCaller()
            val session = checkedSession(sessionId)
            synchronized(gate) {
                if (session in forgottenSessions) throw SecurityException("closed config session")
                if (session !in liveSessions && liveSessions.size >= 32)
                    throw SecurityException("too many live sessions")
                liveSessions.add(session)
            }
            // Registry contains typed mount settings only; no provider credentials or args file bytes.
            return checkedRegistry().toString()
        }
        override fun previewCreateMount(sessionId: String?, typedMount: String?): String =
            previewConfigTicket(sessionId, "create", "", typedMount)
        override fun previewEditMount(sessionId: String?, originalName: String?, typedMount: String?): String =
            previewConfigTicket(sessionId, "edit", originalName, typedMount)
        override fun previewDeleteMount(sessionId: String?, mountName: String?): String =
            previewConfigTicket(sessionId, "delete", mountName, null)

        private fun previewConfigTicket(sessionId: String?, action: String,
            originalName: String?, typedMount: String?): String {
            authenticatedCaller()
            val session = checkedSession(sessionId)
            if (action !in setOf("create", "edit", "delete")) throw SecurityException("unreviewed config operation")
            val before = checkedRegistry()
            val revision = before.getLong("revision")
            val entries = before.getJSONArray("mounts")
            val name = originalName ?: ""
            if (action != "create" && !jobName.matches(name)) throw SecurityException("bad original mount name")
            val previous = (0 until entries.length()).map { entries.getJSONObject(it) }
            val target = previous.firstOrNull { it.getString("name") == name }
            if (action != "create" && target == null) throw SecurityException("original mount missing")
            val spec = if (action == "delete") null else checkedMountDraft(typedMount)
            if (spec != null) {
                // Native editor accepts configured provider remotes only, not arbitrary paths
                // or user-supplied credential/config files.
                val remoteName = spec.getString("remote").substringBefore(':')
                if (remoteName !in checkedConfiguredRemotes())
                    throw SecurityException("mount source is not a configured remote")
            }
            if (action == "create" && previous.any { it.getString("name") == spec!!.getString("name") })
                throw SecurityException("duplicate mount name")
            if (action == "edit" && spec!!.getString("name") != name)
                throw SecurityException("renaming a mount is unsupported")
            val candidate = JSONArray()
            previous.forEach { if (action == "create" || it.getString("name") != name) candidate.put(it) }
            if (spec != null) candidate.put(spec)
            val assembled = JSONObject().put("schema_version", 2).put("revision", revision)
                .put("mounts", candidate)
            val raw = assembled.toString()
            if (raw.length > 65_536) throw SecurityException("oversized registry candidate")
            // Independent daemon validation precedes the daemon's revision/digest-bound proof.
            val validation = rpc("config.validate", "query", JSONObject().put("candidate", assembled))
            if (validation.opt("ok") != true) {
                val issues = validation.optJSONObject("error")?.optJSONArray("field_errors")
                // No untrusted daemon messages or values are propagated. Only a
                // targeted, whitelisted field code for this new/edited mount.
                if (issues != null && issues.length() == 1) {
                    val item = issues.optJSONObject(0)
                    val field = item?.optString("field") ?: ""
                    val code = item?.optString("code") ?: ""
                    if (item?.optInt("index", -1) == candidate.length() - 1 &&
                        field in setOf("name", "remote", "mountpoint", "vfs_profile", "cache_mode",
                            "network_mode", "log_level", "cache_max_bytes", "min_cache_free_bytes",
                            "cache_max_age_seconds", "dir_cache_seconds", "poll_seconds",
                            "min_battery_percent", "boot_settle_seconds", "network_settle_seconds",
                            "cache_low_percent", "cache_high_percent") &&
                        code in setOf("INVALID_OR_DUPLICATE", "INVALID_REMOTE", "INVALID_PATH",
                            "OUTSIDE_SUPPORTED_STORAGE", "PATH_TOO_LONG", "OVERLAPPING_DESTINATION",
                            "INVALID_CHOICE", "OUT_OF_RANGE", "EXCEEDS_HIGH_WATERMARK")) {
                        return JSONObject().put("field_errors", JSONArray().put(JSONObject()
                            .put("field", field).put("code", code))).toString()
                    }
                }
                throw IOException("daemon rejected mount configuration")
            }
            val validated = requireResult(validation)
            if (validated.getLong("revision") != revision || validated.getJSONArray("mounts").length() != candidate.length())
                throw IOException("config validation returned inconsistent registry")
            val plan = requireResult(rpc("config.preview", "preview", JSONObject().put("candidate", assembled)))
            if (plan.getLong("base_revision") != revision ||
                !Regex("[a-f0-9]{64}").matches(plan.getString("candidate_digest")))
                throw IOException("invalid config preview identity")
            val proof = plan.getString("proof")
            if (proof.length !in 16..2048) throw IOException("invalid config proof")
            val effects = plan.getJSONArray("effects")
            if (effects.length() !in 1..64) throw SecurityException("no changes or oversized diff")
            val affected = (0 until effects.length()).map { effects.getJSONObject(it) }
            val affectedName = if (action == "create") spec!!.getString("name") else name
            if (affected.none { it.optString("name") == affectedName } ||
                affected.any { it.optString("name") != affectedName || it.optString("change") !in
                    setOf("create", "update", "delete") }) throw IOException("unexpected config diff")
            val id = UUID.randomUUID().toString()
            synchronized(gate) {
                val now = SystemClock.elapsedRealtime()
                configTickets.entries.removeAll { it.value.deadline <= now || it.value.session == session }
                if (session in forgottenSessions || session !in liveSessions)
                    throw SecurityException("closed config session")
                if (configTickets.size >= 8) throw SecurityException("too many pending config previews")
                configTickets[id] = ConfigTicket(session, action, affectedName, raw,
                    proof, revision, now + 60_000L)
            }
            // App gets only a scoped ticket and a human-readable diff, never the daemon proof.
            return JSONObject().put("id", id).put("action", action).put("name", affectedName)
                .put("base_revision", revision)
                .put("effects", JSONArray(affected.map { "${it.getString("change")}: ${it.getString("name")}" }))
                .put("remote", spec?.optString("remote") ?: target?.optString("remote") ?: "")
                .put("mountpoint", spec?.optString("mountpoint") ?: target?.optString("mountpoint") ?: "").toString()
        }
        override fun applyMountConfiguration(sessionId: String?, previewId: String?): String {
            authenticatedCaller()
            val session = checkedSession(sessionId)
            if (previewId == null || !uuid.matches(previewId)) throw SecurityException("invalid config preview ticket")
            // Destructive / ambiguous result never reuses a ticket, even if the daemon times out.
            val ticket = synchronized(gate) { configTickets.remove(previewId) }
                ?: throw SecurityException("config preview already consumed")
            if (ticket.session != session || ticket.deadline <= SystemClock.elapsedRealtime())
                throw SecurityException("foreign or expired config preview")
            synchronized(gate) {
                if (session in forgottenSessions || session !in liveSessions)
                    throw SecurityException("config session closed")
            }
            if (checkedRegistry().getLong("revision") != ticket.revision)
                throw SecurityException("config revision changed after preview")
            val outcome = requireResult(rpc("config.apply", "run", JSONObject()
                .put("candidate", JSONObject(ticket.candidate)).put("proof", ticket.proof)))
            if (outcome.getLong("revision") != ticket.revision + 1 ||
                outcome.getInt("schema_version") != 2 ||
                outcome.getJSONArray("mounts").length() > 64)
                throw IOException("config application result not verified")
            return JSONObject().put("name", ticket.name).put("action", ticket.action)
                .put("revision", outcome.getLong("revision")).put("refresh_required", true).toString()
        }
        /** Whole-registry rollback uses daemon's previous-known-good state, never UI JSON. */
        override fun previewRollbackMountConfiguration(sessionId: String?): String {
            authenticatedCaller()
            val session = checkedSession(sessionId)
            val before = checkedRegistry()
            val revision = before.getLong("revision")
            synchronized(gate) {
                if (session in forgottenSessions || session !in liveSessions)
                    throw SecurityException("closed rollback session")
            }
            val plan = requireResult(rpc("config.rollback.preview", "preview", JSONObject()))
            if (plan.getLong("base_revision") != revision ||
                !Regex("[a-f0-9]{64}").matches(plan.getString("candidate_digest")))
                throw IOException("rollback revision or digest mismatch")
            val proof = plan.getString("proof")
            if (proof.length !in 16..2048) throw IOException("invalid daemon rollback proof")
            val effects = plan.getJSONArray("effects")
            if (effects.length() !in 1..64) throw SecurityException("empty or oversized rollback changes")
            val descriptions = JSONArray()
            for (i in 0 until effects.length()) {
                val item = effects.getJSONObject(i)
                val name = item.getString("name")
                if (!jobName.matches(name) || item.getString("change") !in setOf("create", "update", "delete"))
                    throw IOException("unreviewed rollback effect")
                descriptions.put(item.getString("change") + ": " + name)
            }
            val id = UUID.randomUUID().toString()
            synchronized(gate) {
                val now = SystemClock.elapsedRealtime()
                rollbackTickets.entries.removeAll { it.value.deadline <= now || it.value.session == session }
                if (session in forgottenSessions || session !in liveSessions)
                    throw SecurityException("rollback session closed during preview")
                if (rollbackTickets.size >= 8) throw SecurityException("too many rollback previews")
                rollbackTickets[id] = RollbackTicket(session, proof, revision, now + 60_000L)
            }
            return JSONObject().put("id", id).put("base_revision", revision)
                .put("effects", descriptions).put("scope", "ENTIRE_REGISTRY").toString()
        }
        override fun applyRollbackMountConfiguration(sessionId: String?, previewId: String?): String {
            authenticatedCaller()
            val session = checkedSession(sessionId)
            if (previewId == null || !uuid.matches(previewId))
                throw SecurityException("invalid rollback ticket")
            val ticket = synchronized(gate) { rollbackTickets.remove(previewId) }
                ?: throw SecurityException("rollback ticket already consumed")
            if (ticket.session != session || ticket.deadline <= SystemClock.elapsedRealtime())
                throw SecurityException("foreign or expired rollback ticket")
            synchronized(gate) {
                if (session in forgottenSessions || session !in liveSessions)
                    throw SecurityException("rollback session closed")
            }
            if (checkedRegistry().getLong("revision") != ticket.revision)
                throw SecurityException("registry changed since rollback preview")
            // The previous-known-good candidate remains daemon-owned; no client
            // registry body or arbitrary root operation may be submitted.
            val outcome = requireResult(rpc("config.rollback", "run",
                JSONObject().put("proof", ticket.proof)))
            if (outcome.getInt("schema_version") != 2 ||
                outcome.getLong("revision") != ticket.revision + 1 ||
                outcome.getJSONArray("mounts").length() > 64)
                throw IOException("rollback result identity not verified")
            return JSONObject().put("revision", outcome.getLong("revision"))
                .put("refresh_required", true).put("scope", "ENTIRE_REGISTRY").toString()
        }
        override fun forgetSession(sessionId: String?) {
            authenticatedCaller()
            val session = checkedSession(sessionId)
            synchronized(gate) {
                tickets.entries.removeAll { it.value.session == session }
                mountTickets.entries.removeAll { it.value.session == session }
                configTickets.entries.removeAll { it.value.session == session }
                rollbackTickets.entries.removeAll { it.value.session == session }
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
            "mount.list", "mount.status", "jobs.status", "operation.events", "provider.browse")
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
        if (op == "mount.status") {
            if (input.length() != 1 || !input.has("name"))
                throw SecurityException("mount status requires an exact name")
            val name = input.optString("name", "")
            if (!jobName.matches(name)) throw SecurityException("invalid mount name")
            return JSONObject().put("name", name)
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

    /** Read back the real owned mount identity immediately before issuing a mutation. */
    private fun checkedConfiguredRemotes(): Set<String> {
        val envelope = rpc("provider.remotes", "query", JSONObject())
        if (envelope.opt("ok") != true) throw IOException("remote registry unavailable")
        val values = envelope.optJSONArray("result") ?: throw IOException("remote inventory malformed")
        if (values.length() > 128) throw IOException("remote inventory exceeds editor limit")
        val remoteNames = mutableSetOf<String>()
        for (i in 0 until values.length()) {
            val name = values.getJSONObject(i).getString("name")
            if (!Regex("[A-Za-z0-9_.-]{1,64}").matches(name) || !remoteNames.add(name))
                throw IOException("unsafe remote inventory")
        }
        return remoteNames
    }

    /** Exact public mount schema, no unknown fields, no credentials, no hidden args file. */
    private fun checkedMountDraft(raw: String?): JSONObject {
        if (raw == null || raw.length !in 2..8192) throw SecurityException("invalid mount draft size")
        val source = JSONObject(raw)
        val stringFields = setOf("name", "remote", "mountpoint", "vfs_profile", "cache_mode", "log_level", "network_mode")
        val booleanFields = setOf("enabled", "allow_other", "read_only", "charging_only")
        val longFields = setOf("cache_max_bytes", "cache_max_age_seconds", "dir_cache_seconds",
            "poll_seconds", "min_cache_free_bytes")
        val intFields = setOf("min_battery_percent", "boot_settle_seconds", "network_settle_seconds",
            "cache_high_percent", "cache_low_percent")
        val names = stringFields + booleanFields + longFields + intFields
        if (source.length() != names.size || source.keys().asSequence().toSet() != names)
            throw SecurityException("missing or unrecognized mount fields")
        for (key in stringFields) if (source.opt(key) !is String)
            throw SecurityException("invalid mount text type")
        for (key in booleanFields) if (source.opt(key) !is Boolean)
            throw SecurityException("invalid mount boolean type")
        for (key in longFields + intFields) if (source.opt(key) !is Number ||
            !Regex("[0-9]{1,16}").matches(source.opt(key).toString()) ||
            source.getLong(key) < 0)
            throw SecurityException("invalid mount numeric type")
        if (!jobName.matches(source.getString("name")) ||
            source.getString("remote").length > 1024 || source.getString("mountpoint").length > 256)
            throw SecurityException("invalid config input bounds")
        return source
    }
    private fun checkedRegistry(): JSONObject {
        val result = requireResult(rpc("config.snapshot", "query", JSONObject()))
        if (result.getInt("schema_version") != 2 || result.getLong("revision") < 0)
            throw IOException("unsupported mount registry")
        val mounts = result.getJSONArray("mounts")
        if (mounts.length() > 64 || result.toString().length > 65_536)
            throw IOException("registry is outside native editor limits")
        val seen = mutableSetOf<String>()
        for (i in 0 until mounts.length()) {
            val name = mounts.getJSONObject(i).getString("name")
            if (!jobName.matches(name) || !seen.add(name))
                throw IOException("unsafe mount registry identity")
        }
        return result
    }

    private fun checkedMountState(name: String): JSONObject {
        val state = requireResult(rpc("mount.status", "query", JSONObject().put("name", name)))
        if (state.optString("name") != name ||
            state.optString("observed") !in setOf("RUNNING", "STOPPED", "DEGRADED", "MOUNT_STALE") ||
            state.opt("desired") !is Boolean || state.optInt("pid", 0) < 0)
            throw IOException("invalid authoritative mount state")
        return state
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
            socket.soTimeout = if (op == "provider.browse" ||
                op in setOf("mount.start", "mount.stop", "mount.restart", "mount.reconcile", "config.apply", "config.rollback")) 35_000 else 8_000
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
