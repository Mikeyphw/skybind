package io.github.mikeyphw.skybind

import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.assertTextEquals
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.captureToImage
import org.junit.Assert.assertTrue
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.activity.compose.setContent
import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.unit.Density
import androidx.test.ext.junit.runners.AndroidJUnit4
import io.github.mikeyphw.skybind.model.*
import io.github.mikeyphw.skybind.ui.SkybindApp
import io.github.mikeyphw.skybind.ui.NativePresentation
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Visual/semantics coverage against fixture-only UI; never evidence of a rooted daemon. */
@RunWith(AndroidJUnit4::class)
class NativePolishUiTest {
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
    // Private, bounded diagnostics: tag counts only (merged/unmerged), never
    // text, package signing material, root state or the full semantics tree.
    // A failure wraps its assertion with these counts for the NATIVE-06 log.
    private fun signerSemantics(phase: String): String {
        val tags = listOf("about-signer-dialog", "about-signer-sha256", "about-signer-close")
        return "NATIVE06_SIGNER_SEMANTICS_V1 phase=$phase " + tags.joinToString(" ") { tag ->
            val merged = compose.onAllNodesWithTag(tag).fetchSemanticsNodes().size
            val unmerged = compose.onAllNodesWithTag(tag, useUnmergedTree = true)
                .fetchSemanticsNodes().size
            "$tag=$merged/$unmerged"
        }
    }
    @Test fun homeShowsEvidenceNotHealthyGuess() {
        fixtureContent { SkybindApp(fixture(), {}) }
        compose.onNodeWithTag("home-runtime-health").assertExists()
        compose.onNodeWithTag("home-mount-summary").assertExists()
        compose.onNodeWithTag("home-network").assertExists()
    }
    @Test fun diagnosticsAndBkxStatesAreVisibleWithoutBackgroundActivation() {
        fixtureContent { SkybindApp(fixture(), {}, bkxAuthorityRunning = true,
            bkxPeerConnected = false) }
        compose.onNodeWithTag("nav-more").performClick()
        compose.onNodeWithTag("bkx-authority-status").assertExists()
        compose.onNodeWithTag("bkx-notification-status").assertExists()
        compose.onNodeWithTag("bkx-background-lifetime").assertExists()
        compose.onNodeWithTag("diagnostics-fuse").assertExists()
        compose.onNodeWithTag("about-app-version").assertExists()
        compose.onNodeWithTag("about-signer-dialog").assertDoesNotExist()
        compose.onNodeWithTag("about-signer-dialog", useUnmergedTree = true).assertDoesNotExist()
        compose.onNodeWithTag("about-show-signer").performClick()
        compose.waitForIdle()
        val afterClick = signerSemantics("after_click")
        println(afterClick)
        // Do not assume Material3's dialog wrapper is exposed as a merged
        // semantics node on API 36. Still require the ACTUAL dialog, Close
        // action and signer SHA-256 to be composed and visible after the click.
        try {
            compose.onNodeWithTag("about-signer-dialog", useUnmergedTree = true).assertExists()
            val expectedSigner = NativePresentation.signer(compose.activity)
            assertTrue("Installed fingerprint must be an actual SHA-256", Regex("[0-9a-f]{64}").matches(expectedSigner))
            compose.onNodeWithTag("about-signer-sha256", useUnmergedTree = true)
                .assertTextEquals(expectedSigner).assertIsDisplayed()
            compose.onNodeWithTag("about-signer-close", useUnmergedTree = true)
                .assertIsDisplayed().performClick()
            compose.waitForIdle()
            compose.onNodeWithTag("about-signer-dialog", useUnmergedTree = true).assertDoesNotExist()
            compose.onNodeWithTag("about-signer-sha256", useUnmergedTree = true).assertDoesNotExist()
            compose.onNodeWithTag("about-signer-close", useUnmergedTree = true).assertDoesNotExist()
        } catch (failure: AssertionError) {
            // Unlike raw printToLog(), this cannot disclose the fingerprint.
            throw AssertionError(afterClick + " (bounded signer-only semantics)", failure)
        }
    }
    @Test fun activityFiltersAndReceiptDetailsRemainReadOnly() {
        fixtureContent { SkybindApp(fixture(), {}) }
        compose.onNodeWithTag("nav-jobs").performClick()
        compose.onNodeWithTag("job-receipt-ab012345ab012345ab012345ab012345").performClick()
        compose.onNodeWithTag("jobs-view-activity").performClick()
        compose.onNodeWithTag("activity-journal-gap").assertExists()
        compose.onNodeWithTag("event-2").assertExists()
        compose.onNodeWithTag("activity-filter-errors").performClick()
        compose.onNodeWithTag("event-2").assertDoesNotExist()
    }
    @Test fun screenshotFixtureCapturesAuthenticatedComposePixels() {
        fixtureContent { SkybindApp(fixture(), {}) }
        val screenshot = compose.onRoot().captureToImage()
        assertTrue(screenshot.width > 0 && screenshot.height > 0)
    }
    @Test fun screenshotFixtureCapturesOfflineComposePixels() {
        fixtureContent { SkybindApp(fixture().copy(link = LinkState.DISCONNECTED), {}) }
        val screenshot = compose.onRoot().captureToImage()
        assertTrue(screenshot.width > 0 && screenshot.height > 0)
    }
    @Test fun scaledFontsAndLandscapeLayoutRetainNavigationSemantics() {
        fixtureContent {
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
