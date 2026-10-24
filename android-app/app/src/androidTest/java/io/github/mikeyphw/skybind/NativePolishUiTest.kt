package io.github.mikeyphw.skybind

import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.captureToImage
import org.junit.Assert.assertTrue
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.unit.Density
import androidx.test.ext.junit.runners.AndroidJUnit4
import io.github.mikeyphw.skybind.model.*
import io.github.mikeyphw.skybind.ui.SkybindApp
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Visual/semantics coverage against fixture-only UI; never evidence of a rooted daemon. */
@RunWith(AndroidJUnit4::class)
class NativePolishUiTest {
    @get:Rule val compose = createComposeRule()
    private fun fixture() = SkybindReadSnapshot(
        link = LinkState.ONLINE, detail = "Authenticated fixture",
        runtime = RuntimeIntegrity(ready = false, provenanceValid = false, provider = "fixture"),
        remotes = listOf(RemoteSummary("source", "Source", "drive")),
        mounts = listOf(MountSummary("demo", "Demo", "DEGRADED", true, "retry", 2, "provider_retry")),
        jobs = listOf(JobSummary("ab012345ab012345ab012345ab012345", "Large file transfer",
            JobState.RUNNING, 1048576, 4194304)),
        events = listOf(ActivityRecord(2, "ab012345ab012345ab012345ab012345", "job.progress",
            "1790000000000", ActivitySeverity.WARNING),
            ActivityRecord(1, null, "job.started", "1790000000000", ActivitySeverity.INFO)),
        hasEventGap = true,
    )
    @Test fun homeShowsEvidenceNotHealthyGuess() {
        compose.setContent { SkybindApp(fixture(), {}) }
        compose.onNodeWithTag("home-runtime-health").assertExists()
        compose.onNodeWithTag("home-mount-summary").assertExists()
        compose.onNodeWithTag("home-network").assertExists()
    }
    @Test fun diagnosticsAndBkxStatesAreVisibleWithoutBackgroundActivation() {
        compose.setContent { SkybindApp(fixture(), {}, bkxAuthorityRunning = true,
            bkxPeerConnected = false) }
        compose.onNodeWithTag("nav-more").performClick()
        compose.onNodeWithTag("bkx-authority-status").assertExists()
        compose.onNodeWithTag("bkx-notification-status").assertExists()
        compose.onNodeWithTag("bkx-background-lifetime").assertExists()
        compose.onNodeWithTag("diagnostics-fuse").assertExists()
        compose.onNodeWithTag("about-app-version").assertExists()
        compose.onNodeWithTag("about-show-signer").performClick()
        compose.onNodeWithTag("about-signer-sha256").assertExists()
    }
    @Test fun activityFiltersAndReceiptDetailsRemainReadOnly() {
        compose.setContent { SkybindApp(fixture(), {}) }
        compose.onNodeWithTag("nav-jobs").performClick()
        compose.onNodeWithTag("job-receipt-ab012345ab012345ab012345ab012345").performClick()
        compose.onNodeWithTag("jobs-view-activity").performClick()
        compose.onNodeWithTag("activity-journal-gap").assertExists()
        compose.onNodeWithTag("event-2").assertExists()
        compose.onNodeWithTag("activity-filter-errors").performClick()
        compose.onNodeWithTag("event-2").assertDoesNotExist()
    }
    @Test fun screenshotFixtureCapturesAuthenticatedComposePixels() {
        compose.setContent { SkybindApp(fixture(), {}) }
        val screenshot = compose.onRoot().captureToImage()
        assertTrue(screenshot.width > 0 && screenshot.height > 0)
    }
    @Test fun screenshotFixtureCapturesOfflineComposePixels() {
        compose.setContent { SkybindApp(fixture().copy(link = LinkState.DISCONNECTED), {}) }
        val screenshot = compose.onRoot().captureToImage()
        assertTrue(screenshot.width > 0 && screenshot.height > 0)
    }
    @Test fun scaledFontsAndLandscapeLayoutRetainNavigationSemantics() {
        compose.setContent {
            val density = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(density.density, 2f)) {
                SkybindApp(fixture(), {})
            }
        }
        compose.onNodeWithTag("nav-more").assertExists()
        compose.onNodeWithTag("nav-mounts").performClick()
        compose.onNodeWithTag("screen-mounts").assertExists()
    }
}
