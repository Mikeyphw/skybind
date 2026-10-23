package io.github.mikeyphw.skybind

import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import io.github.mikeyphw.skybind.model.*
import io.github.mikeyphw.skybind.ui.SkybindApp
import org.junit.Rule
import org.junit.Test
import org.junit.Assert.assertEquals
import org.junit.runner.RunWith

/** Test-only fixtures never become a production backend or a broker. */
@RunWith(AndroidJUnit4::class)
class NativeUiTest {
    @get:Rule val compose = createComposeRule()

    private fun fixture() = SkybindReadSnapshot(
        link = LinkState.ONLINE, detail = "Fixture-only authenticated session", serverVersion = "fixture-v1",
        remotes = listOf(RemoteSummary("photos", "Photos", "drive"), RemoteSummary("archive", "Archive", "crypt")),
        mounts = listOf(MountSummary("photos", "Photos mount", "RUNNING", true, "owned_fuse_mount")),
        jobs = listOf(
            JobSummary("live-fixture", "Photo copy", JobState.RUNNING, 12L, 24L),
            JobSummary("done-fixture", "Older check", JobState.COMPLETED),
        ),
        events = listOf(
            ActivityRecord(3, "live-fixture", "Copy progressed", "T3", ActivitySeverity.INFO),
            ActivityRecord(2, null, "Connection warning", "T2", ActivitySeverity.WARNING),
            ActivityRecord(1, "done-fixture", "Check completed", "T1", ActivitySeverity.INFO),
        ), cursor = 3,
    )

    @Test fun realNavigationHasFiveDistinctPages() {
        compose.setContent { SkybindApp(SkybindReadSnapshot(LinkState.NOT_AUTHORIZED, "Not paired"), {}) }
        compose.onNodeWithTag("screen-home").assertExists()
        for (page in listOf("mounts", "browser", "jobs", "more")) {
            compose.onNodeWithTag("nav-$page").performClick()
            compose.onNodeWithTag("screen-$page").assertExists()
        }
        compose.onNodeWithTag("auto-connect-switch").assertExists()
    }

    @Test fun mountsHaveDedicatedNavigationAndAuthoritativeStatus() {
        compose.setContent { SkybindApp(fixture(), {}) }
        compose.onNodeWithTag("nav-mounts").performClick()
        compose.onNodeWithTag("screen-mounts").assertExists()
        compose.onNodeWithTag("mount-photos").assertExists()
        compose.onNodeWithTag("browser-write-disabled").assertDoesNotExist()
    }

    @Test fun mountActionsRequireUserGestureAndExplicitConsent() {
        var requested: String? = null
        compose.setContent { SkybindApp(fixture(), {},
            onPreviewMount = { action, name -> requested = "$action:$name" }) }
        compose.onNodeWithTag("nav-mounts").performClick()
        compose.onNodeWithTag("mount-start-photos").assertIsNotEnabled()
        compose.onNodeWithTag("mount-stop-photos").assertIsEnabled().performClick()
        compose.runOnIdle { assertEquals("stop:photos", requested) }
    }

    @Test fun mountConfirmationNeverRunsWithoutCheckboxConsent() {
        var submitted = 0
        compose.setContent { SkybindApp(fixture(), {},
            mountPreview = PreparedMountAction("f7bf6776-6ee3-4520-bbfb-9f55e327c7c1", "stop", "photos", "RUNNING", true),
            onConfirmMount = { submitted++ }) }
        compose.onNodeWithTag("mount-action-dialog").assertExists()
        compose.onNodeWithTag("mount-action-confirm").assertIsNotEnabled()
        compose.onNodeWithTag("mount-action-consent").performClick()
        compose.onNodeWithTag("mount-action-confirm").assertIsEnabled().performClick()
        compose.runOnIdle { assertEquals(1, submitted) }
    }

    @Test fun unpairedMountActionsAreNotAvailable() {
        compose.setContent { SkybindApp(fixture().copy(link = LinkState.NOT_AUTHORIZED), {}) }
        compose.onNodeWithTag("nav-mounts").performClick()
        compose.onNodeWithTag("mount-stop-photos").assertDoesNotExist()
        compose.onNodeWithTag("mount-action-dialog").assertDoesNotExist()
    }

    @Test fun activityIsAJournalNotAnActionableJobQueue() {
        compose.setContent { SkybindApp(fixture(), {}) }
        compose.onNodeWithTag("nav-jobs").performClick()
        compose.onNodeWithTag("job-live-fixture").assertExists()
        compose.onNodeWithTag("job-done-fixture").assertExists()
        compose.onNodeWithTag("cancel-live-fixture").assertIsNotEnabled()
        compose.onNodeWithTag("event-3").assertDoesNotExist()
        compose.onNodeWithTag("jobs-view-activity").performClick()
        compose.onNodeWithTag("screen-activity").assertExists()
        compose.onNodeWithTag("event-3").assertExists()
        compose.onNodeWithTag("event-2").assertExists()
        compose.onNodeWithTag("job-live-fixture").assertDoesNotExist()
        compose.onNodeWithTag("activity-filter-warnings").performClick()
        compose.onNodeWithTag("event-2").assertExists()
        compose.onNodeWithTag("event-3").assertDoesNotExist()
    }

    @Test fun browserDoesNotOfferWritesOrInventContents() {
        compose.setContent { SkybindApp(fixture(), {}) }
        compose.onNodeWithTag("nav-browser").performClick()
        compose.onNodeWithTag("remote-photos").assertExists()
        compose.onNodeWithTag("remote-archive").assertExists()
        compose.onNodeWithTag("browser-search").performTextInput("Photo")
        compose.onNodeWithTag("remote-photos").assertExists()
        compose.onNodeWithTag("remote-archive").assertDoesNotExist()
        compose.onNodeWithTag("browser-write-disabled").assertIsNotEnabled()
    }

    @Test fun unpairedStateHidesStaleServerData() {
        val stale = fixture().copy(link = LinkState.DISCONNECTED, detail = "No authenticated session")
        compose.setContent { SkybindApp(stale, {}) }
        compose.onNodeWithTag("nav-jobs").performClick()
        compose.onNodeWithTag("job-live-fixture").assertDoesNotExist()
        compose.onNodeWithTag("nav-more").performClick()
        compose.onNodeWithTag("more-view-activity").performClick()
        compose.onNodeWithTag("event-3").assertDoesNotExist()
        compose.onNodeWithTag("nav-browser").performClick()
        compose.onNodeWithTag("remote-photos").assertDoesNotExist()
        // Offline Browser deliberately omits the search control; it must not expose stale remote state.
        compose.onNodeWithTag("browser-search").assertDoesNotExist()
    }
}
