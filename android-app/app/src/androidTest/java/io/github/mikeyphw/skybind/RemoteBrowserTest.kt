package io.github.mikeyphw.skybind

import androidx.compose.ui.test.assertDoesNotExist
import androidx.compose.ui.test.assertExists
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import io.github.mikeyphw.skybind.bridge.RemoteBrowseReader
import io.github.mikeyphw.skybind.model.*
import io.github.mikeyphw.skybind.ui.SkybindApp
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class RemoteBrowserTest {
    @get:Rule val compose = createComposeRule()
    private fun snapshot() = SkybindReadSnapshot(LinkState.ONLINE, "Fixture only",
        remotes = listOf(RemoteSummary("alpha", "Alpha", "drive")))

    @Test fun listsRealFoldersAndKeepsWritesDisabled() {
        compose.setContent { SkybindApp(snapshot(), {}, {}, BrowserState("alpha", "",
            listOf(RemoteFileEntry("folder", true, 0), RemoteFileEntry("data.txt", false, 12))),
            onBrowseFolder = {}) }
        compose.onNodeWithTag("nav-browser").performClick()
        compose.onNodeWithTag("folder-folder").assertExists()
        compose.onNodeWithTag("file-data.txt").assertExists()
        compose.onNodeWithTag("browser-write-disabled").assertExists()
    }

    @Test fun disconnectedStateHidesFormerContents() {
        compose.setContent { SkybindApp(SkybindReadSnapshot(LinkState.DISCONNECTED, "Offline"), {}, {},
            BrowserState("alpha", "secret", listOf(RemoteFileEntry("private", false, 5)))) }
        compose.onNodeWithTag("nav-browser").performClick()
        compose.onNodeWithTag("file-private").assertDoesNotExist()
        compose.onNodeWithTag("browser-path").assertDoesNotExist()
    }

    @Test fun requestUsesTypedBoundedRemoteEndpoint() {
        val entries = RemoteBrowseReader().fetch("alpha", "dir") { op, args ->
            assertEquals("provider.browse", op)
            assertTrue(args.contains("alpha:dir"))
            """{"schema_version":1,"ok":true,"result":[{"Path":"dir/a","Name":"a","Size":8,"IsDir":false}]}"""
        }
        assertEquals("a", entries.single().name)
        assertFalse(entries.single().directory)
    }

    @Test fun rejectsEscapesAndUntrustedListing() {
        for (path in listOf("../bad", "/absolute", "a//b", "a:b", "a/./b")) {
            assertTrue(runCatching { BrowseAddress.endpoint("alpha", path) }.isFailure)
        }
        assertTrue(runCatching {
            RemoteBrowseReader().fetch("alpha", "") { _, _ ->
                """{"schema_version":1,"ok":true,"result":[{"Path":"../escape","Name":"a","Size":8,"IsDir":false}]}"""
            }
        }.isFailure)
    }
}
