package io.github.mikeyphw.skybind

import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.activity.compose.setContent
import androidx.compose.runtime.Composable
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
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()
    // Run fixture UI inside the already-declared TARGET package activity.
    // Do not call compose.setContent(): MainActivity sets its own content onCreate.
    // Replacing its composition is test-only and adds no manifest components.
    private fun fixtureContent(content: @Composable () -> Unit) {
        val activity = compose.activity  // resolve outside the main thread
        compose.runOnUiThread { activity.setContent(content = content) }
        compose.waitForIdle()
    }


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
        fixtureContent { SkybindApp(SkybindReadSnapshot(LinkState.NOT_AUTHORIZED, "Not paired"), {}) }
        compose.onNodeWithTag("screen-home").assertExists()
        for (page in listOf("mounts", "browser", "jobs", "more")) {
            compose.onNodeWithTag("nav-$page").performClick()
            compose.onNodeWithTag("screen-$page").assertExists()
        }
        compose.onNodeWithTag("auto-connect-switch").assertExists()
    }

    @Test fun mountsHaveDedicatedNavigationAndAuthoritativeStatus() {
        fixtureContent { SkybindApp(fixture(), {}) }
        compose.onNodeWithTag("nav-mounts").performClick()
        compose.onNodeWithTag("screen-mounts").assertExists()
        compose.onNodeWithTag("mount-photos").assertExists()
        compose.onNodeWithTag("browser-write-disabled").assertDoesNotExist()
    }

    @Test fun mountActionsRequireUserGestureAndExplicitConsent() {
        var requested: String? = null
        fixtureContent { SkybindApp(fixture(), {},
            onPreviewMount = { action, name -> requested = "$action:$name" }) }
        compose.onNodeWithTag("nav-mounts").performClick()
        compose.onNodeWithTag("mount-start-photos").assertIsNotEnabled()
        compose.onNodeWithTag("mount-stop-photos").assertIsEnabled().performClick()
        compose.runOnIdle { assertEquals("stop:photos", requested) }
    }

    @Test fun mountConfirmationNeverRunsWithoutCheckboxConsent() {
        var submitted = 0
        fixtureContent { SkybindApp(fixture(), {},
            mountPreview = PreparedMountAction("f7bf6776-6ee3-4520-bbfb-9f55e327c7c1", "stop", "photos", "RUNNING", true),
            onConfirmMount = { submitted++ }) }
        compose.onNodeWithTag("mount-action-dialog").assertExists()
        compose.onNodeWithTag("mount-action-confirm").assertIsNotEnabled()
        compose.onNodeWithTag("mount-action-consent").performClick()
        compose.onNodeWithTag("mount-action-confirm").assertIsEnabled().performClick()
        compose.runOnIdle { assertEquals(1, submitted) }
    }

    @Test fun nativeMountConfigurationOpensFromTheMountsTab() {
        var action: String? = null
        fixtureContent { SkybindApp(fixture(), {}, onOpenMountConfig = { selected, _ -> action = selected }) }
        compose.onNodeWithTag("nav-mounts").performClick()
        compose.onNodeWithTag("mount-add").assertExists().performClick()
        compose.runOnIdle { assertEquals("create", action) }
        compose.onNodeWithTag("mount-edit-photos").performClick()
        compose.runOnIdle { assertEquals("edit", action) }
        compose.onNodeWithTag("mount-delete-photos").performClick()
        compose.runOnIdle { assertEquals("delete", action) }
    }

    @Test fun configApplyRequiresReviewConsent() {
        var applies = 0
        fixtureContent { SkybindApp(fixture(), {},
            mountConfigMode = "delete", mountConfigDraft = MountDraft(name = "photos"),
            mountConfigPreview = PreparedConfigChange(
                "f7bf6776-6ee3-4520-bbfb-9f55e327c7c1", "delete", "photos", 4,
                listOf("delete: photos"), "/storage/emulated/0/Photos", "photos:"),
            onApplyMountConfig = { applies++ }) }
        compose.onNodeWithTag("config-editor-dialog").assertExists()
        compose.onNodeWithTag("config-apply").assertIsNotEnabled()
        compose.onNodeWithTag("config-consent").performClick()
        compose.onNodeWithTag("config-apply").assertIsEnabled().performClick()
        compose.runOnIdle { assertEquals(1, applies) }
    }

    @Test fun unpairedMountActionsAreNotAvailable() {
        fixtureContent { SkybindApp(fixture().copy(link = LinkState.NOT_AUTHORIZED), {}) }
        compose.onNodeWithTag("nav-mounts").performClick()
        compose.onNodeWithTag("mount-stop-photos").assertDoesNotExist()
        compose.onNodeWithTag("mount-action-dialog").assertDoesNotExist()
    }

    @Test fun activityIsAJournalNotAnActionableJobQueue() {
        fixtureContent { SkybindApp(fixture(), {}) }
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
        fixtureContent { SkybindApp(fixture(), {}) }
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
        fixtureContent { SkybindApp(stale, {}) }
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
