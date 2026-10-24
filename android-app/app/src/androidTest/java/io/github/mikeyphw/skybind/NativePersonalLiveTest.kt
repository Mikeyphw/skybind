package io.github.mikeyphw.skybind

import android.app.Application
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.assertExists
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import io.github.mikeyphw.skybind.bridge.RootReadSession
import io.github.mikeyphw.skybind.model.MountDraft
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Live rooted PERSONAL acceptance only. No fixture states are accepted as daemon truth.
 * Disposable mutations require explicit ADB test arguments and an isolated registry.
 */
@RunWith(AndroidJUnit4::class)
class NativePersonalLiveTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()

    private fun optedIn() =
        assumeTrue("NATIVE_PERSONAL_LIVE_NOT_REQUESTED",
            InstrumentationRegistry.getArguments().getString("skybind.native.personal.live") == "true")

    @Test fun automaticForegroundRootNoManualConnect() {
        optedIn()
        compose.onNodeWithTag("screen-home").assertExists()
        // No Connect or Retry click permitted. Root manager grant is an external prerequisite.
        compose.waitUntil(75_000L) {
            compose.onAllNodes(androidx.compose.ui.test.hasTestTag("disconnect-readonly"))
                .fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithTag("disconnect-readonly").assertExists()
    }

    @Test fun mountsMatchAuthoritativeDaemon() = runBlocking {
        optedIn()
        val application = InstrumentationRegistry.getInstrumentation()
            .targetContext.applicationContext as Application
        val root = RootReadSession(application) {}
        try {
            root.connect()
            val snapshot = root.snapshot()
            assertTrue("real authenticated daemon required", snapshot.online)
            val registry = root.loadMountRegistry()
            assertEquals(registry.mounts.map { it.name }.toSet(),
                snapshot.mounts.map { it.id }.toSet())
            assertTrue(snapshot.mounts.all {
                it.state in setOf("RUNNING", "STOPPED", "DEGRADED", "MOUNT_STALE")
            })
        } finally {
            root.close()
        }
    }

    @Test fun disposableMountStartRestartStopReconcile() = runBlocking {
        val args = InstrumentationRegistry.getArguments()
        assumeTrue("NATIVE_PERSONAL_LIFECYCLE_NOT_AUTHORIZED",
            args.getString("skybind.native.personal.lifecycle") == "true" &&
            args.getString("skybind.native.personal.reconcile") == "true")
        val remoteName = args.getString("skybind.native.personal.remote") ?: ""
        assertTrue(Regex("[A-Za-z0-9_.-]{1,64}").matches(remoteName))
        val application = InstrumentationRegistry.getInstrumentation()
            .targetContext.applicationContext as Application
        val root = RootReadSession(application) {}
        // Host acceptance runner creates exactly this empty test-owned directory
        // before the instrumented test. The daemon never creates mountpoints.
        val name = args.getString("skybind.native.personal.mountname") ?: ""
        val mountpoint = args.getString("skybind.native.personal.mountpoint") ?: ""
        assertTrue(Regex("NativeLife[0-9a-f]{12}").matches(name))
        assertEquals("/storage/emulated/0/Download/.skybind-native-" + name, mountpoint)
        var created = false
        try {
            root.connect()
            val initial = root.snapshot()
            assertTrue(initial.online && initial.remotes.any { it.id == remoteName })
            val before = root.loadMountRegistry()
            // Reconcile is registry-wide. Don't run it where any unrelated mount could
            // be started/stopped by reconciliation, regardless of owner consent.
            assertTrue("global reconcile requires isolated inactive registry",
                before.mounts.all { !it.enabled } &&
                initial.mounts.none { it.state == "RUNNING" })
            val draft = MountDraft(name = name, remote = "$remoteName:",
                mountpoint = mountpoint,
                enabled = true, readOnly = true)
            val create = root.previewConfig("create", "", draft)
            root.applyConfig(create)
            created = true
            val start = root.previewMount("start", name)
            assertEquals("start", start.action)
            root.confirmMount(start)
            val running = root.snapshot().mounts.single { it.id == name }
            assertEquals("RUNNING", running.state)
            val restart = root.previewMount("restart", name)
            assertEquals("restart", restart.action)
            root.confirmMount(restart)
            val afterRestart = root.snapshot().mounts.single { it.id == name }
            assertEquals("RUNNING", afterRestart.state)
            val stop = root.previewMount("stop", name)
            assertEquals("stop", stop.action)
            root.confirmMount(stop)
            val stopped = root.snapshot().mounts.single { it.id == name }
            assertEquals("STOPPED", stopped.state)
            val reconcile = root.previewMount("reconcile", "")
            assertEquals("reconcile", reconcile.action)
            root.confirmMount(reconcile)
            val afterward = root.loadMountRegistry()
            assertEquals(before.mounts, afterward.mounts.filterNot { it.name == name })
        } finally {
            if (created) {
                // Fail the test if the mount cannot be stopped/cleaned. No force-delete.
                val current = root.snapshot()
                val owned = current.mounts.firstOrNull { it.id == name }
                if (owned != null && owned.state != "STOPPED") {
                    val stop = root.previewMount("stop", name)
                    root.confirmMount(stop)
                    assertEquals("STOPPED", root.snapshot().mounts.single { it.id == name }.state)
                }
                val delete = root.previewConfig("delete", name, null)
                root.applyConfig(delete)
                assertFalse(root.loadMountRegistry().mounts.any { it.name == name })
            }
            root.close()
        }
    }
}
