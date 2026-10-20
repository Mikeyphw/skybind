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

/**
 * Opt-in REAL RootService negative acceptance, with no grant changes, daemon
 * termination, forced app process death, shell, remote mutation or write calls.
 * A denied/unavailable existing grant is BLOCKED, not fabricated as a PASS.
 */
@RunWith(AndroidJUnit4::class)
class LiveNegativeAcceptanceTest {
    @Test fun liveReadOnlyNegativeBoundaries() = runBlocking {
        val options = InstrumentationRegistry.getArguments()
        assumeTrue("SKYBIND_NEGATIVE_NOT_REQUESTED",
            options.getString("skybind.negative.live") == "true")
        val requested = options.getString("skybind.remote")?.takeIf { it.isNotEmpty() }
        if (requested != null && !Regex("[A-Za-z0-9][A-Za-z0-9_-]{0,63}").matches(requested))
            throw AssertionError("SKYBIND_NEGATIVE_FAILED_UNSAFE_REMOTE_SELECTION")
        val app = ApplicationProvider.getApplicationContext<Application>()
        val session = RootReadSession(app) {}
        try {
            val before = session.snapshot()
            assertEquals("SKYBIND_NEGATIVE_FAILED_IMPLICIT_ROOT_ACCESS",
                LinkState.NOT_AUTHORIZED, before.link)
            assertTrue("SKYBIND_NEGATIVE_FAILED_STALE_UNPAIRED", before.remotes.isEmpty() &&
                before.activeJobs.isEmpty() && before.timeline.isEmpty() && before.cursor == null)

            withTimeout(90_000L) {
                try {
                    withContext(Dispatchers.Main) { session.connect() }
                } catch (_: Exception) {
                    throw AssertionError("SKYBIND_NEGATIVE_BLOCKED_ROOT_BIND")
                }
            }
            val live = session.snapshot()
            when (live.link) {
                LinkState.ONLINE -> Unit
                LinkState.NOT_AUTHORIZED -> throw AssertionError("SKYBIND_NEGATIVE_BLOCKED_ROOT_AUTH")
                LinkState.DISCONNECTED -> throw AssertionError("SKYBIND_NEGATIVE_BLOCKED_DAEMON")
                LinkState.UNSUPPORTED -> throw AssertionError("SKYBIND_NEGATIVE_FAILED_API_MISMATCH")
                else -> throw AssertionError("SKYBIND_NEGATIVE_FAILED_UNEXPECTED_LINK")
            }
            val remote = requested ?: live.remotes.map { it.id }.sorted().firstOrNull()
                ?: throw AssertionError("SKYBIND_NEGATIVE_BLOCKED_NO_REMOTE")
            if (live.remotes.none { it.id == remote })
                throw AssertionError("SKYBIND_NEGATIVE_BLOCKED_REMOTE_NOT_CONFIGURED")
            // Both are rejected in the app before reaching the privileged daemon.
            for (pair in listOf(remote to "../escape", "invalid:remote" to "")) {
                var refused = false
                try {
                    session.browse(pair.first, pair.second)
                } catch (_: IllegalArgumentException) {
                    refused = true
                }
                assertTrue("SKYBIND_NEGATIVE_FAILED_UNSAFE_BROWSE_ACCEPTED", refused)
            }
            val stillLive = session.snapshot()
            assertEquals("SKYBIND_NEGATIVE_FAILED_NEGATIVE_READ_POISONED_SESSION",
                LinkState.ONLINE, stillLive.link)
            withContext(Dispatchers.Main) { session.close() }
            val offline = session.snapshot()
            assertEquals("SKYBIND_NEGATIVE_FAILED_TEARDOWN_NOT_UNPAIRED",
                LinkState.NOT_AUTHORIZED, offline.link)
            assertTrue("SKYBIND_NEGATIVE_FAILED_TEARDOWN_LEAK", offline.remotes.isEmpty() &&
                offline.activeJobs.isEmpty() && offline.timeline.isEmpty() && offline.cursor == null)
        } finally {
            withContext(NonCancellable + Dispatchers.Main) { session.close() }
        }
    }
}
