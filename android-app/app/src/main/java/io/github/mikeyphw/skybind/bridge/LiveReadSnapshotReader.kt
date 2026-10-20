package io.github.mikeyphw.skybind.bridge

import io.github.mikeyphw.skybind.model.*
import org.json.JSONArray
import org.json.JSONObject

/** Validates real daemon RPC envelopes and authoritative state; no fixture in production. */
class LiveReadSnapshotReader {
    private var cursor: Long = 0
    private var history: List<ActivityRecord> = emptyList()

    @Synchronized fun reset() { cursor = 0; history = emptyList() }

    @Synchronized fun fetch(query: (String, String) -> String): SkybindReadSnapshot {
        fun read(name: String, args: JSONObject = JSONObject()): Any {
            val body = JSONObject(query(name, args.toString()))
            if (body.optInt("schema_version", -1) != 1 || body.opt("ok") != true) {
                throw IllegalStateException("daemon rejected required query")
            }
            return body.opt("result") ?: throw IllegalStateException("missing daemon result")
        }
        val capabilities = read("system.capabilities") as? JSONObject
            ?: return SkybindReadSnapshot(LinkState.UNSUPPORTED, "Unrecognized daemon capability response")
        if (capabilities.optInt("protocol_version", -1) != 1 || capabilities.optInt("total", -1) != 57) {
            reset()
            return SkybindReadSnapshot(LinkState.UNSUPPORTED, "Skybind daemon API does not match this app")
        }
        val supported = mutableSetOf<String>()
        val available = capabilities.optJSONArray("operations") ?: JSONArray()
        for (i in 0 until available.length()) {
            val op = available.optJSONObject(i) ?: continue
            if (op.optBoolean("implemented", false) && op.optString("operation_class") == "query") {
                supported += op.optString("name")
            }
        }
        if (!supported.containsAll(setOf("runtime.status", "provider.remotes", "jobs.status", "mount.list"))) {
            reset()
            return SkybindReadSnapshot(LinkState.UNSUPPORTED, "Daemon is missing required read-only capabilities")
        }
        // operation.events is an additive extension and does not appear in the frozen
        // 57-operation catalog; query it independently, fail closed on absence.
        val runtime = read("runtime.status") as? JSONObject ?: error("invalid runtime response")
        val remotes = read("provider.remotes") as? JSONArray ?: error("invalid remotes response")
        val mounts = read("mount.list") as? JSONArray ?: error("invalid mounts response")
        val jobs = read("jobs.status") as? JSONObject ?: error("invalid jobs response")
        val page = read("operation.events", JSONObject().put("cursor", cursor).put("limit", 64)
            .put("operation_id", "").put("wait_ms", 0)) as? JSONObject ?: error("invalid event response")

        val remoteItems = (0 until remotes.length()).map { i ->
            val obj = remotes.getJSONObject(i)
            val name = obj.getString("name")
            require(name.isNotBlank() && name.length <= 96)
            RemoteSummary(name, name, obj.optString("type", "unknown").take(48))
        }.take(128)
        val mountItems = (0 until mounts.length()).map { i ->
            val name = mounts.getString(i)
            require(name.isNotBlank() && name.length <= 96)
            MountSummary(name, name, "Not queried")
        }.take(128)
        val registry = jobs.getJSONObject("registry")
        val entries = registry.getJSONArray("jobs")
        require(entries.length() <= 128)
        val definitions = (0 until entries.length()).map { i ->
            val obj = entries.getJSONObject(i)
            val name = obj.getString("name")
            val kind = obj.getString("kind")
            require(Regex("[A-Za-z][A-Za-z0-9_-]{0,62}").matches(name))
            require(kind in setOf("check", "copy", "sync"))
            JobDefinition(name, kind, obj.getBoolean("enabled"))
        }
        require(definitions.map { it.name }.toSet().size == definitions.size)
        val runs = jobs.getJSONArray("runs")
        val runItems = (0 until runs.length()).map { i ->
            val obj = runs.getJSONObject(i)
            val id = obj.getString("id")
            require(Regex("[0-9a-f]{32}").matches(id))
            val state = when (obj.optString("state").uppercase()) {
                "QUEUED" -> JobState.QUEUED
                "RUNNING" -> JobState.RUNNING
                "INTERRUPTED" -> JobState.INTERRUPTED
                "COMPLETED" -> JobState.COMPLETED
                "FAILED" -> JobState.FAILED
                "CANCELLED" -> JobState.CANCELLED
                else -> throw IllegalStateException("unknown run state")
            }
            val total = if (obj.has("total_bytes") && !obj.isNull("total_bytes")) obj.getLong("total_bytes") else null
            val bytes = obj.optLong("bytes", 0)
            require(bytes >= 0 && (total == null || total >= 0))
            fun nonnegative(key: String): Long? {
                if (!obj.has(key) || obj.isNull(key)) return null
                val value = obj.getLong(key)
                require(value >= 0)
                return value
            }
            val speed = if (obj.has("speed_bytes_per_second") && !obj.isNull("speed_bytes_per_second"))
                obj.getDouble("speed_bytes_per_second").also { require(it.isFinite() && it >= 0.0) } else null
            val percent = if (obj.has("percent") && !obj.isNull("percent"))
                obj.getDouble("percent").also { require(it.isFinite() && it in 0.0..100.0) } else null
            JobSummary(id, obj.optString("name", "Job").take(96), state, bytes, total,
                speed, nonnegative("eta_seconds"), percent, nonnegative("files_done"), nonnegative("files_total"))
        }.takeLast(128)
        val reset = page.optBoolean("cursor_reset") || page.optBoolean("gap")
        val newCursor = page.getLong("next_cursor")
        if (newCursor < 0 || newCursor < cursor && !reset) throw IllegalStateException("event cursor went backwards")
        val events = page.getJSONArray("events")
        val collected = mutableListOf<ActivityRecord>()
        var prev = if (reset) 0L else cursor
        for (i in 0 until events.length()) {
            val e = events.getJSONObject(i)
            val seq = e.getLong("sequence")
            require(seq > prev && seq <= page.optLong("latest_cursor", Long.MAX_VALUE))
            prev = seq
            val typ = e.getString("type")
            val severity = when {
                typ.endsWith("failed") -> ActivitySeverity.ERROR
                typ.endsWith("interrupted") || typ.endsWith("cancelling") -> ActivitySeverity.WARNING
                else -> ActivitySeverity.INFO
            }
            collected += ActivityRecord(seq, e.optString("operation_id").takeIf { it.isNotBlank() },
                typ.take(90), e.optLong("unix_millis").toString(), severity)
        }
        if (events.length() > 0 && prev > newCursor) throw IllegalStateException("invalid event continuation")
        cursor = newCursor
        history = (if (reset) emptyList() else history).plus(collected)
            .distinctBy { it.sequence }.takeLast(100)
        val degraded = page.optBoolean("degraded") || page.optBoolean("gap") || page.optBoolean("cursor_reset")
        return SkybindReadSnapshot(
            link = LinkState.ONLINE,
            detail = if (degraded) "Connected · event journal gap/degraded" else "Connected · read-only root service",
            serverVersion = "Skybind protocol 1 · ${runtime.optString("provider", "runtime")}",
            remotes = remoteItems, mounts = mountItems, jobs = runItems, events = history,
            cursor = cursor, hasEventGap = degraded, definitions = definitions,
        )
    }
}
