package io.github.mikeyphw.skybind

import android.app.Application
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import io.github.mikeyphw.skybind.bridge.RootReadSession
import io.github.mikeyphw.skybind.model.LinkState
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

/** M3 read-only preview authorization against a real daemon-configured check/copy job.
 * Never calls startPreparedJob or cancelOwnedRun. Missing job is BLOCKED, not PASS.
 */
@RunWith(AndroidJUnit4::class)
class LiveM3PreviewAcceptanceTest {
    @Test fun liveM3ReadOnlyJobPreview() = runBlocking {
        assumeTrue("SKYBIND_M3_NOT_REQUESTED",
            InstrumentationRegistry.getArguments().getString("skybind.m3.preview.live") == "true")
        val app = ApplicationProvider.getApplicationContext<Application>()
        val session = RootReadSession(app) { }
        try {
            try { withTimeout(90_000L) { withContext(Dispatchers.Main) { session.connect() } } }
            catch (_: Exception) { throw AssertionError("SKYBIND_M3_BLOCKED_ROOT_BIND") }
            val snapshot = session.snapshot()
            if (snapshot.link != LinkState.ONLINE) throw AssertionError("SKYBIND_M3_BLOCKED_DAEMON")
            val selected = snapshot.definitions.firstOrNull { it.kind == "check" || it.kind == "copy" }
                ?: throw AssertionError("SKYBIND_M3_BLOCKED_NO_ELIGIBLE_JOB")
            val preview = try { session.previewJob(selected.name) }
                catch (_: Exception) { throw AssertionError("SKYBIND_M3_FAILED_PREVIEW_REJECTED") }
            assertEquals("SKYBIND_M3_FAILED_PREVIEW_IDENTITY", selected.name, preview.name)
            assertEquals("SKYBIND_M3_FAILED_PREVIEW_CLASS", selected.kind, preview.kind)
            assertTrue("SKYBIND_M3_FAILED_PREVIEW_FIELDS", preview.id.isNotBlank() &&
                preview.source.isNotBlank() && preview.destination.isNotBlank())
            // No job run/cancel is issued, even if the server allows a preview.
            withContext(Dispatchers.Main) { session.close() }
            val after = session.snapshot()
            assertEquals("SKYBIND_M3_FAILED_SESSION_CLEARED", LinkState.NOT_AUTHORIZED, after.link)
            assertTrue("SKYBIND_M3_FAILED_STALE_JOBS", after.jobs.isEmpty() &&
                after.definitions.isEmpty() && after.events.isEmpty())
        } finally {
            withContext(NonCancellable + Dispatchers.Main) { session.close() }
        }
    }
}
