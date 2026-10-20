package io.github.mikeyphw.skybind

import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.onAllNodes
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Live, explicitly opted-in UI gate. Only the real MainActivity / ViewModel / RootService
 * and its configured remote are used. No fixtures, writes, daemon stop, shell or root grant automation.
 * The disconnect gesture only closes the app-owned session; process-death/root-revocation
 * gates are deliberately OUT OF SCOPE.
 */
@RunWith(AndroidJUnit4::class)
class LiveUiAcceptanceTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()

    private fun tags(prefix: String): List<String> = compose.onAllNodes(
        SemanticsMatcher("test tag prefix") { node ->
            node.config.getOrNull(SemanticsProperties.TestTag)?.startsWith(prefix) == true
        }, useUnmergedTree = true
    ).fetchSemanticsNodes().mapNotNull { it.config.getOrNull(SemanticsProperties.TestTag) }

    private fun awaitTag(tag: String, millis: Long = 70_000L) {
        compose.waitUntil(millis) { tags(tag).contains(tag) }
        compose.onNodeWithTag(tag).assertExists()
    }

    private fun step(code: String, f: () -> Unit) {
        try { f() } catch (e: AssertionError) {
            if (e.message?.startsWith("SKYBIND_UI_") == true) throw e
            throw AssertionError(code)
        } catch (_: Exception) {
            throw AssertionError(code)
        }
    }

    @Test fun liveUiReadOnlyNavigationRecovery() {
        val options = InstrumentationRegistry.getArguments()
        assumeTrue("SKYBIND_UI_NOT_REQUESTED", options.getString("skybind.ui.live") == "true")
        val requested = options.getString("skybind.remote")?.takeIf { it.isNotEmpty() }
        if (requested != null && !Regex("[A-Za-z0-9][A-Za-z0-9_-]{0,63}").matches(requested))
            throw AssertionError("SKYBIND_UI_FAILED_REMOTE_SELECTION")

        step("SKYBIND_UI_FAILED_INITIAL_UNPAIRED") {
            awaitTag("screen-home")
            compose.onNodeWithTag("connect-readonly").assertExists()
            compose.onNodeWithTag("disconnect-readonly").assertDoesNotExist()
        }
        step("SKYBIND_UI_BLOCKED_CONNECT") {
            compose.onNodeWithTag("connect-readonly").performClick()
            awaitTag("disconnect-readonly")
        }
        step("SKYBIND_UI_FAILED_BROWSER_NAVIGATION") {
            compose.onNodeWithTag("nav-browser").performClick()
            awaitTag("browser-search")
            compose.onNodeWithTag("browser-write-disabled").assertIsNotEnabled()
        }
        val remote = requested ?: tags("remote-").firstOrNull()?.removePrefix("remote-")
            ?: throw AssertionError("SKYBIND_UI_BLOCKED_NO_REMOTE")
        // The source is the real button list, not a test-fixture or invented remote.
        if ("remote-$remote" !in tags("remote-"))
            throw AssertionError("SKYBIND_UI_BLOCKED_REMOTE_NOT_VISIBLE")
        step("SKYBIND_UI_FAILED_BROWSER_ROOT") {
            compose.onNodeWithTag("remote-$remote").performClick()
            awaitTag("browser-path")
            compose.waitUntil(50_000L) { "browser-loading" !in tags("browser-loading") }
            compose.onAllNodesWithText("$remote:/", substring = true).fetchSemanticsNodes().let {
                assertTrue("SKYBIND_UI_FAILED_BROWSER_ROOT", it.isNotEmpty())
            }
            assertTrue("SKYBIND_UI_FAILED_BROWSER_ROOT", "browser-error" !in tags("browser-error"))
        }
        val folder = tags("folder-").firstOrNull()?.removePrefix("folder-")
            ?: throw AssertionError("SKYBIND_UI_BLOCKED_NO_FOLDER")
        step("SKYBIND_UI_FAILED_FOLDER_NAVIGATION") {
            compose.onNodeWithTag("folder-$folder").performScrollTo().performClick()
            awaitTag("browser-path")
            compose.waitUntil(50_000L) { "browser-loading" !in tags("browser-loading") }
            assertTrue("SKYBIND_UI_FAILED_FOLDER_NAVIGATION", "browser-error" !in tags("browser-error"))
            compose.waitUntil(10_000L) {
                compose.onAllNodesWithText("$remote:$folder", substring = true)
                    .fetchSemanticsNodes().isNotEmpty()
            }
            compose.onNodeWithTag("browser-up").performClick()
            awaitTag("browser-path")
            compose.waitUntil(50_000L) { "browser-loading" !in tags("browser-loading") }
            compose.waitUntil(10_000L) {
                compose.onAllNodesWithText("$remote:/", substring = true)
                    .fetchSemanticsNodes().isNotEmpty()
            }
            assertTrue("SKYBIND_UI_FAILED_FOLDER_NAVIGATION", "browser-error" !in tags("browser-error"))
            compose.onNodeWithTag("browser-write-disabled").assertIsNotEnabled()
            compose.onNodeWithTag("browser-switch-remote").performClick()
            awaitTag("browser-search")
        }
        step("SKYBIND_UI_FAILED_JOBS_ACTIVITY") {
            compose.onNodeWithTag("nav-jobs").performClick()
            awaitTag("screen-jobs")
            assertTrue("SKYBIND_UI_FAILED_JOBS_ACTIVITY", tags("event-").isEmpty())
            compose.onNodeWithTag("jobs-view-activity").performClick()
            awaitTag("screen-activity")
            assertTrue("SKYBIND_UI_FAILED_JOBS_ACTIVITY", tags("job-").isEmpty())
            compose.onNodeWithTag("activity-filter-warnings").performClick()
            compose.onNodeWithTag("activity-view-jobs").performClick()
            awaitTag("screen-jobs")
        }
        step("SKYBIND_UI_FAILED_ACTIVITY_RECREATE") {
            compose.activityRule.scenario.recreate()
            awaitTag("screen-jobs")
            compose.onNodeWithTag("nav-browser").performClick()
            awaitTag("browser-search") // retained online session; no unauthorized reconnect
        }
        step("SKYBIND_UI_FAILED_DISCONNECT_CLEANUP") {
            compose.onNodeWithTag("nav-home").performClick()
            awaitTag("disconnect-readonly")
            compose.onNodeWithTag("disconnect-readonly").performClick()
            awaitTag("connect-readonly")
            compose.onNodeWithTag("nav-browser").performClick()
            compose.onNodeWithTag("browser-search").assertDoesNotExist()
            assertTrue("SKYBIND_UI_FAILED_DISCONNECT_CLEANUP", tags("remote-").isEmpty())
            compose.onNodeWithTag("nav-jobs").performClick()
            assertTrue("SKYBIND_UI_FAILED_DISCONNECT_CLEANUP", tags("job-").isEmpty())
            compose.onNodeWithTag("nav-activity").performClick()
            assertTrue("SKYBIND_UI_FAILED_DISCONNECT_CLEANUP", tags("event-").isEmpty())
        }
        step("SKYBIND_UI_FAILED_RECONNECT") {
            compose.onNodeWithTag("nav-home").performClick()
            compose.onNodeWithTag("connect-readonly").performClick()
            awaitTag("disconnect-readonly")
            compose.onNodeWithTag("nav-browser").performClick()
            awaitTag("browser-search")
            assertTrue("SKYBIND_UI_FAILED_RECONNECT", "remote-$remote" in tags("remote-"))
        }
    }
}
