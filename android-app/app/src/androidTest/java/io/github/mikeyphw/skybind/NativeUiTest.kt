package io.github.mikeyphw.skybind

import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import io.github.mikeyphw.skybind.model.*
import io.github.mikeyphw.skybind.ui.SkybindApp
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Test-only fixtures never become a production backend or a broker. */
@RunWith(AndroidJUnit4::class)
class NativeUiTest {
    @get:Rule val compose = createComposeRule()

    private fun fixture() = SkybindReadSnapshot(
        link = LinkState.ONLINE, detail = "Fixture-only authenticated session", serverVersion = "fixture-v1",
        remotes = listOf(RemoteSummary("photos", "Photos", "drive"), RemoteSummary("archive", "Archive", "crypt")),
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
        for (page in listOf("browser", "jobs", "activity", "more")) {
            compose.onNodeWithTag("nav-$page").performClick()
            compose.onNodeWithTag("screen-$page").assertExists()
        }
        compose.onNodeWithTag("more-mount-control-disabled").assertIsNotEnabled()
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
        compose.onNodeWithTag("nav-activity").performClick()
        compose.onNodeWithTag("event-3").assertDoesNotExist()
        compose.onNodeWithTag("nav-browser").performClick()
        compose.onNodeWithTag("remote-photos").assertDoesNotExist()
        compose.onNodeWithTag("browser-search").assertIsNotEnabled()
    }
}
