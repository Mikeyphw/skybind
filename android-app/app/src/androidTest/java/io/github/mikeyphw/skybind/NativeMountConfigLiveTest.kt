package io.github.mikeyphw.skybind

import android.app.Application
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import io.github.mikeyphw.skybind.bridge.RootReadSession
import io.github.mikeyphw.skybind.model.MountDraft
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.util.UUID

/**
 * Explicitly authorized disposable actual-root acceptance; NEVER runs in
 * ordinary CI, or without a configured remote selected by the operator.
 * All candidate entries are DISABLED, and no provider files are written.
 */
@RunWith(AndroidJUnit4::class)
class NativeMountConfigLiveTest {
    @Test fun guardedDisposableCreateEditRollbackDelete(): Unit = runBlocking {
        val args = InstrumentationRegistry.getArguments()
        assumeTrue("requires explicit operator opt-in", args.getString("skybind.native.config.allow_disposable") == "true")
        val selectedRemote = args.getString("skybind.native.config.remote") ?: ""
        assumeTrue("explicit remote required", Regex("[A-Za-z0-9_.-]{1,64}").matches(selectedRemote))
        val application = InstrumentationRegistry.getInstrumentation().targetContext.applicationContext as Application
        val root = RootReadSession(application) {}
        val name = "NativeConfig" + UUID.randomUUID().toString().replace("-", "").take(12)
        val draft = MountDraft(name = name, remote = "$selectedRemote:",
            mountpoint = "/storage/emulated/0/Download/.skybind-native-$name", enabled = false,
            readOnly = true)
        var applied = false
        try {
            root.connect()
            val live = root.snapshot()
            assertTrue("authenticated read-only snapshot required", live.online)
            assertTrue("remote must already be configured", live.remotes.any { it.id == selectedRemote })
            val before = root.loadMountRegistry()
            assertFalse("test-owned mount name unexpectedly exists", before.mounts.any { it.name == name })
            val others = before.mounts
            val create = root.previewConfig("create", "", draft)
            assertEquals("create", create.action)
            root.applyConfig(create)
            applied = true
            val created = root.loadMountRegistry()
            assertEquals(others, created.mounts.filterNot { it.name == name })
            assertEquals(draft, created.mounts.single { it.name == name })

            val changedDraft = draft.copy(chargingOnly = true)
            val edit = root.previewConfig("edit", name, changedDraft)
            assertEquals("edit", edit.action)
            root.applyConfig(edit)
            val changed = root.loadMountRegistry()
            assertEquals(changedDraft, changed.mounts.single { it.name == name })
            assertEquals(others, changed.mounts.filterNot { it.name == name })

            // Server-owned previous-known-good candidate; UI never supplies JSON.
            val rollback = root.previewRollback()
            assertEquals(changed.revision, rollback.baseRevision)
            assertTrue(rollback.effects.any { it.contains(name) })
            root.applyRollback(rollback)
            val restored = root.loadMountRegistry()
            assertEquals(draft, restored.mounts.single { it.name == name })
            assertEquals(others, restored.mounts.filterNot { it.name == name })

            val delete = root.previewConfig("delete", name, null)
            assertEquals("delete", delete.action)
            root.applyConfig(delete)
            val completed = root.loadMountRegistry()
            assertEquals(others, completed.mounts)
            applied = false
        } finally {
            if (applied) {
                // A failed cleanup is a failed acceptance, not a silent pass.
                val current = root.loadMountRegistry()
                if (current.mounts.any { it.name == name }) {
                    val cleanup = root.previewConfig("delete", name, null)
                    root.applyConfig(cleanup)
                    assertFalse(root.loadMountRegistry().mounts.any { it.name == name })
                }
            }
            root.close()
        }
    }
}
