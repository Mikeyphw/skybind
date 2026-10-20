package io.github.mikeyphw.skybind

import androidx.test.ext.junit.runners.AndroidJUnit4
import io.github.mikeyphw.skybind.bridge.LiveReadSnapshotReader
import io.github.mikeyphw.skybind.model.LinkState
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class LiveReadGatewayTest {
    private val required = listOf("runtime.status", "provider.remotes", "mount.list", "jobs.status")
    private fun envelope(value: Any): String = JSONObject().put("schema_version", 1)
        .put("request_id", "fixture").put("ok", true).put("result", value).toString()
    private fun capabilities(): JSONObject = JSONObject().put("protocol_version", 1).put("total", 57)
        .put("operations", JSONArray(required.map { name -> JSONObject()
            .put("name", name).put("operation_class", "query").put("implemented", true) }))
    private fun fixture(op: String, args: String = "{}") = envelope(when (op) {
        "system.capabilities" -> capabilities()
        "runtime.status" -> JSONObject().put("provider", "fixture")
        "provider.remotes" -> JSONArray().put(JSONObject().put("name", "photos").put("type", "drive"))
        "mount.list" -> JSONArray().put("photos")
        "jobs.status" -> JSONObject().put("registry", JSONObject()
            .put("schema_version", 1).put("revision", 1).put("jobs", JSONArray()))
            .put("runs", JSONArray().put(JSONObject()
            .put("id", "0123456789abcdef0123456789abcdef").put("name", "copy")
            .put("state", "RUNNING").put("bytes", 16).put("total_bytes", 32)))
        "operation.events" -> JSONObject().put("latest_cursor", 2)
            .put("next_cursor", 2).put("events", JSONArray()
                .put(JSONObject().put("sequence", 2).put("type", "job.progress")
                    .put("operation_id", "0123456789abcdef0123456789abcdef").put("unix_millis", 1000)))
        else -> error("unexpected request")
    })

    @Test fun mapsRealDaemonShapeIntoJobsAndChronologicalActivity() {
        val result = LiveReadSnapshotReader().fetch(::fixture)
        assertEquals(LinkState.ONLINE, result.link)
        assertEquals("photos", result.remotes.single().id)
        assertEquals("photos", result.mounts.single().id)
        assertEquals(16L, result.activeJobs.single().transferredBytes)
        assertEquals(2L, result.cursor)
        assertEquals("job.progress", result.timeline.single().title)
    }

    @Test fun rejectsWrongProtocolInsteadOfInventingOnline() {
        val result = LiveReadSnapshotReader().fetch { op, args ->
            if (op == "system.capabilities") envelope(capabilities().put("protocol_version", 99)) else fixture(op, args)
        }
        assertEquals(LinkState.UNSUPPORTED, result.link)
        assertTrue(result.remotes.isEmpty())
    }

    @Test(expected = IllegalStateException::class)
    fun rejectsFailedRpcResponse() {
        LiveReadSnapshotReader().fetch { op, args ->
            if (op == "jobs.status") JSONObject().put("schema_version", 1)
                .put("ok", false).toString() else fixture(op, args)
        }
    }

    @Test fun repeatedEventCursorMustResumeFromServerValue() {
        val seen = mutableListOf<Long>()
        val reader = LiveReadSnapshotReader()
        repeat(2) {
            reader.fetch { op, args ->
                if (op == "operation.events") {
                    seen += JSONObject(args).getLong("cursor")
                    envelope(JSONObject().put("latest_cursor", 2)
                        .put("next_cursor", 2).put("events", JSONArray()))
                } else fixture(op, args)
            }
        }
        assertEquals(listOf(0L, 2L), seen)
    }

    @Test(expected = IllegalArgumentException::class)
    fun rejectsDuplicateOrRewoundEventSequence() {
        LiveReadSnapshotReader().fetch { op, args ->
            if (op == "operation.events") envelope(JSONObject()
                .put("latest_cursor", 2).put("next_cursor", 2)
                .put("events", JSONArray().put(JSONObject().put("sequence", 2).put("type", "job.started"))
                    .put(JSONObject().put("sequence", 2).put("type", "job.progress"))))
            else fixture(op, args)
        }
    }

    @Test fun gapResetsPreviouslyObservedEvents() {
        val reader = LiveReadSnapshotReader()
        reader.fetch(::fixture)
        val after = reader.fetch { op, args ->
            if (op == "operation.events") envelope(JSONObject().put("latest_cursor", 5)
                .put("next_cursor", 5).put("gap", true).put("events", JSONArray()))
            else fixture(op, args)
        }
        assertTrue(after.hasEventGap)
        assertTrue(after.events.isEmpty())
    }
}
