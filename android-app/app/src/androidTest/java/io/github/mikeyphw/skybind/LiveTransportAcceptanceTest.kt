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

/** M2-L3 controlled local transport-loss simulation against a REAL read-only RootService.
 * Does not kill the daemon, revoke root grants, force-stop an app or write a remote.
 * It must not be reported as evidence of actual daemon death or root revocation.
 */
@RunWith(AndroidJUnit4::class)
class LiveTransportAcceptanceTest {
    @Test fun liveTransportLossAndFreshReconnect() = runBlocking {
        val args = InstrumentationRegistry.getArguments()
        assumeTrue("SKYBIND_TRANSPORT_NOT_REQUESTED", args.getString("skybind.transport.live") == "true")
        val app = ApplicationProvider.getApplicationContext<Application>()
        var losses = 0
        val session = RootReadSession(app) { losses++ }
        try {
            assertEquals("SKYBIND_TRANSPORT_FAILED_UNPAIRED", LinkState.NOT_AUTHORIZED,
                session.snapshot().link)
            try {
                withTimeout(90_000L) { withContext(Dispatchers.Main) { session.connect() } }
            } catch (_: Exception) {
                throw AssertionError("SKYBIND_TRANSPORT_BLOCKED_BIND")
            }
            val first = session.snapshot()
            if (first.link == LinkState.NOT_AUTHORIZED)
                throw AssertionError("SKYBIND_TRANSPORT_BLOCKED_ROOT_AUTH")
            if (first.link == LinkState.DISCONNECTED)
                throw AssertionError("SKYBIND_TRANSPORT_BLOCKED_DAEMON")
            assertEquals("SKYBIND_TRANSPORT_FAILED_INITIAL_READ", LinkState.ONLINE, first.link)
            withContext(Dispatchers.Main) { session.transportLost() }
            assertEquals("SKYBIND_TRANSPORT_FAILED_CALLBACK_COUNT", 1, losses)
            withContext(Dispatchers.Main) { session.transportLost() }
            assertEquals("SKYBIND_TRANSPORT_FAILED_DUPLICATE_CALLBACK", 1, losses)
            val stale = session.snapshot()
            assertEquals("SKYBIND_TRANSPORT_FAILED_STALE_AUTHORITY", LinkState.NOT_AUTHORIZED, stale.link)
            assertTrue("SKYBIND_TRANSPORT_FAILED_STALE_DATA", stale.remotes.isEmpty() &&
                stale.jobs.isEmpty() && stale.events.isEmpty() && stale.cursor == null)
            try {
                withTimeout(90_000L) { withContext(Dispatchers.Main) { session.connect() } }
            } catch (_: Exception) {
                throw AssertionError("SKYBIND_TRANSPORT_BLOCKED_REBIND")
            }
            val fresh = session.snapshot()
            assertEquals("SKYBIND_TRANSPORT_FAILED_RECONNECT", LinkState.ONLINE, fresh.link)
        } finally {
            withContext(NonCancellable + Dispatchers.Main) { session.close() }
        }
    }
}
