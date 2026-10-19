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
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Explicitly selected real-substrate acceptance. Never a fixture, auto-root
 * grant, shell or synthetic provider. This uses only read-only daemon queries.
 * The root manager's grant must be approved by the operator.
 */
@RunWith(AndroidJUnit4::class)
class LiveRootBrowserAcceptanceTest {
    @Test fun liveReadBrowseAndReconnect() = runBlocking {
        val opts = InstrumentationRegistry.getArguments()
        assumeTrue("SKYBIND_LIVE_NOT_REQUESTED", opts.getString("skybind.live") == "true")
        val requestedRemote = opts.getString("skybind.remote")?.takeIf { it.isNotBlank() }
        if (requestedRemote != null &&
            !Regex("[A-Za-z0-9][A-Za-z0-9_-]{0,63}").matches(requestedRemote)) {
            throw AssertionError("SKYBIND_LIVE_INVALID_REMOTE_SELECTION")
        }
        val app = ApplicationProvider.getApplicationContext<Application>()
        val session = RootReadSession(app) {}
        try {
            withTimeout(90_000L) {
                try {
                    withContext(Dispatchers.Main) { session.connect() }
                } catch (_: Exception) {
                    throw AssertionError("SKYBIND_LIVE_BLOCKED_ROOT_BIND")
                }
                val first = session.snapshot()
                when (first.link) {
                    LinkState.NOT_AUTHORIZED -> throw AssertionError("SKYBIND_LIVE_BLOCKED_ROOT_AUTH")
                    LinkState.DISCONNECTED -> throw AssertionError("SKYBIND_LIVE_BLOCKED_DAEMON")
                    LinkState.UNSUPPORTED -> throw AssertionError("SKYBIND_LIVE_FAILED_API_MISMATCH")
                    LinkState.ONLINE -> Unit
                    else -> throw AssertionError("SKYBIND_LIVE_FAILED_UNEXPECTED_LINK")
                }
                assertTrue("SKYBIND_LIVE_FAILED_CURSOR", first.cursor != null && first.cursor >= 0)
                val remote = requestedRemote
                    ?: first.remotes.map { it.id }.sorted().firstOrNull()
                    ?: throw AssertionError("SKYBIND_LIVE_BLOCKED_NO_REMOTE")
                if (first.remotes.none { it.id == remote }) {
                    throw AssertionError("SKYBIND_LIVE_BLOCKED_REMOTE_NOT_CONFIGURED")
                }
                try {
                    val entries = session.browse(remote, "")
                    assertTrue("SKYBIND_LIVE_FAILED_UNBOUNDED_BROWSE", entries.size <= 500)
                } catch (_: Exception) {
                    throw AssertionError("SKYBIND_LIVE_FAILED_BROWSE")
                }
                withContext(Dispatchers.Main) { session.close() }
                val unpaired = session.snapshot()
                assertTrue("SKYBIND_LIVE_FAILED_STALE_AFTER_CLOSE",
                    !unpaired.online && unpaired.remotes.isEmpty() && unpaired.jobs.isEmpty() &&
                    unpaired.events.isEmpty())
                try {
                    withContext(Dispatchers.Main) { session.connect() }
                } catch (_: Exception) {
                    throw AssertionError("SKYBIND_LIVE_FAILED_REBIND")
                }
                val again = session.snapshot()
                assertTrue("SKYBIND_LIVE_FAILED_RECONNECT_SNAPSHOT",
                    again.online && again.remotes.any { it.id == remote } && again.cursor != null)
            }
        } finally {
            withContext(NonCancellable + Dispatchers.Main) { session.close() }
        }
    }
}
