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

/** Real local-media disposable COPY only. External Termux runner verifies all bytes. */
@RunWith(AndroidJUnit4::class)
class LiveM3CopyAcceptanceTest {
    private val name = "M3DisposableCopy"
    private val src = "/storage/emulated/0/Download/.skybind-m3-copy/source"
    private val dst = "/storage/emulated/0/Download/.skybind-m3-copy/destination"
    private suspend fun connect(): RootReadSession {
        val bridge = RootReadSession(ApplicationProvider.getApplicationContext<Application>()) { }
        try { withContext(Dispatchers.Main) { withTimeout(30_000L) { bridge.connect() } } }
        catch (_: Exception) { throw AssertionError("SKYBIND_M3_COPY_BLOCKED_BIND") }
        val snapshot=bridge.snapshot()
        if (snapshot.link != LinkState.ONLINE || snapshot.definitions.none {
                it.name == name && it.enabled && it.kind == "copy" })
            throw AssertionError("SKYBIND_M3_COPY_BLOCKED_FIXTURE")
        return bridge
    }

    @Test fun liveDisposableCopyReconnectReconcile() = runBlocking {
        assumeTrue("SKYBIND_M3_COPY_NOT_REQUESTED",
            InstrumentationRegistry.getArguments().getString("skybind.m3.copy.live") == "true")
        var first: RootReadSession? = null
        var second: RootReadSession? = null
        try {
            val a = connect(); first=a
            val preview=a.previewJob(name)
            assertTrue("SKYBIND_M3_COPY_FAILED_PREVIEW_IDENTITY", preview.name==name &&
                preview.kind=="copy" && preview.source==src && preview.destination==dst)
            val id = try { a.startPreparedJob(preview) }
                catch (_: Exception) { throw AssertionError("SKYBIND_M3_COPY_FAILED_START") }
            // A ticket is one-shot. An ambiguous duplicate must not be retried.
            assertTrue("SKYBIND_M3_COPY_FAILED_DUPLICATE_ACCEPTED",
                runCatching { a.startPreparedJob(preview) }.isFailure)
            withContext(Dispatchers.Main) { a.close() }
            assertEquals("SKYBIND_M3_COPY_FAILED_STALE_SNAPSHOT", LinkState.NOT_AUTHORIZED,a.snapshot().link)
            val b=connect(); second=b
            // The new session does not inherit ownership of the old run.
            assertTrue("SKYBIND_M3_COPY_FAILED_CROSS_SESSION_CANCEL_ACCEPTED",
                runCatching { b.cancelOwnedRun(id) }.isFailure)
            assertTrue("SKYBIND_M3_COPY_FAILED_STALE_PROOF_ACCEPTED",
                runCatching { b.startPreparedJob(preview) }.isFailure)
            var terminal: JobState?=null
            var eventSeen=false
            try {
                withTimeout(150_000L) {
                    while (terminal == null) {
                        val snapshot=b.snapshot()
                        if (!snapshot.online) throw AssertionError("SKYBIND_M3_COPY_FAILED_RECONNECT_SNAPSHOT")
                        eventSeen = eventSeen || snapshot.events.any { it.operationId==id }
                        val state=snapshot.jobs.firstOrNull { it.id==id }?.state
                        if (state in setOf(JobState.COMPLETED, JobState.FAILED, JobState.INTERRUPTED,
                                JobState.CANCELLED)) terminal=state
                        if (terminal == null) delay(750L)
                    }
                }
            } catch (_: kotlinx.coroutines.TimeoutCancellationException) {
                throw AssertionError("SKYBIND_M3_COPY_FAILED_TERMINAL_TIMEOUT")
            }
            assertEquals("SKYBIND_M3_COPY_FAILED_TERMINAL", JobState.COMPLETED,terminal)
            assertTrue("SKYBIND_M3_COPY_FAILED_EVENT_REPLAY",eventSeen)
        } finally {
            withContext(NonCancellable + Dispatchers.Main) { second?.close();first?.close() }
        }
    }
}
