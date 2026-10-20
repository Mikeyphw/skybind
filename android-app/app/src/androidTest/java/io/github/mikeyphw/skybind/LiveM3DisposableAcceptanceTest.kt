package io.github.mikeyphw.skybind

import android.app.Application
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import io.github.mikeyphw.skybind.bridge.RootReadSession
import io.github.mikeyphw.skybind.model.JobState
import io.github.mikeyphw.skybind.model.LinkState
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

/** Real daemon, exact test-owned local-media CHECK only. No implicit fixture creation.
 * Unlike M3 preview, these tests deliberately submit a job and require separate
 * explicit runner authorization. Never issue a raw RPC, arbitrary path or sync.
 */
@RunWith(AndroidJUnit4::class)
class LiveM3DisposableAcceptanceTest {
    private val fixture = "M3DisposableCheck"
    private val source = "/storage/emulated/0/Download/.skybind-m3-disposable/source"
    private val destination = "/storage/emulated/0/Download/.skybind-m3-disposable/destination"

    private suspend fun session(): RootReadSession {
        val app = ApplicationProvider.getApplicationContext<Application>()
        val bridge = RootReadSession(app) { }
        try { withTimeout(30_000L) { withContext(Dispatchers.Main) { bridge.connect() } } }
        catch (_: Exception) { throw AssertionError("SKYBIND_M3_DISPOSABLE_BLOCKED_BIND") }
        val snapshot = bridge.snapshot()
        if (snapshot.link != LinkState.ONLINE)
            throw AssertionError("SKYBIND_M3_DISPOSABLE_BLOCKED_SNAPSHOT")
        if (snapshot.definitions.none { it.name == fixture && it.enabled && it.kind == "check" })
            throw AssertionError("SKYBIND_M3_DISPOSABLE_BLOCKED_FIXTURE")
        return bridge
    }

    private suspend fun prepare(bridge: RootReadSession): io.github.mikeyphw.skybind.model.PreparedJob {
        val preview = try { bridge.previewJob(fixture) }
            catch (_: Exception) { throw AssertionError("SKYBIND_M3_DISPOSABLE_FAILED_PREVIEW") }
        if (preview.name != fixture || preview.kind != "check" ||
            preview.source != source || preview.destination != destination)
            throw AssertionError("SKYBIND_M3_DISPOSABLE_FAILED_FIXTURE_IDENTITY")
        return preview
    }

    @Test fun liveDisposableCheckCompletes() = runBlocking {
        assumeTrue("SKYBIND_M3_DISPOSABLE_NOT_REQUESTED",
            InstrumentationRegistry.getArguments().getString("skybind.m3.execute.live") == "true")
        var bridge: RootReadSession? = null
        try {
            val current = session()
            bridge = current
            val preview = prepare(current)
            val id = try { current.startPreparedJob(preview) }
                catch (_: Exception) { throw AssertionError("SKYBIND_M3_DISPOSABLE_FAILED_START") }
            // Reusing an already consumed ticket must never create a second job.
            val replayRejected = runCatching { current.startPreparedJob(preview) }.isFailure
            assertTrue("SKYBIND_M3_DISPOSABLE_FAILED_REPLAY_ACCEPTED", replayRejected)
            var sawJob = false
            var sawEvent = false
            var terminalState: JobState? = null
            try {
                withTimeout(150_000L) {
                    while (terminalState == null) {
                        val snapshot = current.snapshot()
                        if (!snapshot.online) throw AssertionError("SKYBIND_M3_DISPOSABLE_FAILED_LOST_SNAPSHOT")
                        sawEvent = sawEvent || snapshot.events.any { it.operationId == id }
                        val run = snapshot.jobs.firstOrNull { it.id == id }
                        if (run != null) {
                            sawJob = true
                            if (run.state in setOf(JobState.COMPLETED, JobState.FAILED,
                                    JobState.CANCELLED, JobState.INTERRUPTED)) terminalState = run.state
                        }
                        if (terminalState == null) delay(750L)
                    }
                }
            } catch (e: kotlinx.coroutines.TimeoutCancellationException) {
                throw AssertionError("SKYBIND_M3_DISPOSABLE_FAILED_TERMINAL_TIMEOUT")
            }
            assertEquals("SKYBIND_M3_DISPOSABLE_FAILED_TERMINAL", JobState.COMPLETED, terminalState)
            assertTrue("SKYBIND_M3_DISPOSABLE_FAILED_AUTHORITATIVE_JOB", sawJob)
            assertTrue("SKYBIND_M3_DISPOSABLE_FAILED_EVENT_REPLAY", sawEvent)
            withContext(Dispatchers.Main) { current.close() }
            assertEquals("SKYBIND_M3_DISPOSABLE_FAILED_STALE_AFTER_CLOSE",
                LinkState.NOT_AUTHORIZED, current.snapshot().link)
        } finally {
            withContext(NonCancellable + Dispatchers.Main) { bridge?.close() }
        }
    }

    @Test fun liveDisposableOwnedCancellation() = runBlocking {
        assumeTrue("SKYBIND_M3_DISPOSABLE_NOT_REQUESTED",
            InstrumentationRegistry.getArguments().getString("skybind.m3.cancel.live") == "true")
        var bridge: RootReadSession? = null
        try {
            val current = session()
            bridge = current
            val preview = prepare(current)
            val id = try { current.startPreparedJob(preview) }
                catch (_: Exception) { throw AssertionError("SKYBIND_M3_DISPOSABLE_FAILED_START") }
            // Negative ownership check: arbitrary, non-session run IDs must be denied.
            val foreign = "ffffffffffffffffffffffffffffffff"
            assertTrue("SKYBIND_M3_DISPOSABLE_FAILED_FOREIGN_CANCEL_ACCEPTED",
                runCatching { current.cancelOwnedRun(foreign) }.isFailure)
            try { current.cancelOwnedRun(id) }
            catch (_: Exception) {
                val state = current.snapshot().jobs.firstOrNull { it.id == id }?.state
                if (state == JobState.COMPLETED)
                    throw AssertionError("SKYBIND_M3_DISPOSABLE_BLOCKED_CANCEL_RACE")
                throw AssertionError("SKYBIND_M3_DISPOSABLE_FAILED_OWNED_CANCEL")
            }
            var sawEvent = false
            var terminalState: JobState? = null
            try {
                withTimeout(90_000L) {
                    while (terminalState == null) {
                        val snapshot = current.snapshot()
                        if (!snapshot.online) throw AssertionError("SKYBIND_M3_DISPOSABLE_FAILED_LOST_SNAPSHOT")
                        sawEvent = sawEvent || snapshot.events.any { it.operationId == id }
                        val state = snapshot.jobs.firstOrNull { it.id == id }?.state
                        if (state != null && state in setOf(JobState.CANCELLED, JobState.COMPLETED,
                                JobState.FAILED, JobState.INTERRUPTED)) terminalState = state
                        if (terminalState == null) delay(500L)
                    }
                }
            } catch (_: kotlinx.coroutines.TimeoutCancellationException) {
                throw AssertionError("SKYBIND_M3_DISPOSABLE_FAILED_CANCEL_TIMEOUT")
            }
            if (terminalState == JobState.COMPLETED)
                throw AssertionError("SKYBIND_M3_DISPOSABLE_BLOCKED_CANCEL_RACE")
            assertEquals("SKYBIND_M3_DISPOSABLE_FAILED_CANCEL_TERMINAL", JobState.CANCELLED, terminalState)
            assertTrue("SKYBIND_M3_DISPOSABLE_FAILED_CANCEL_EVENT", sawEvent)
            withContext(Dispatchers.Main) { current.close() }
            assertEquals("SKYBIND_M3_DISPOSABLE_FAILED_STALE_AFTER_CLOSE",
                LinkState.NOT_AUTHORIZED, current.snapshot().link)
        } finally {
            withContext(NonCancellable + Dispatchers.Main) { bridge?.close() }
        }
    }
}
