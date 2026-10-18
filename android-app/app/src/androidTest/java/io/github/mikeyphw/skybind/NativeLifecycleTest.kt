package io.github.mikeyphw.skybind

import androidx.compose.ui.test.assertExists
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Activity recreation is NOT evidence for real force-stop/process death. */
@RunWith(AndroidJUnit4::class)
class NativeLifecycleTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()

    @Test fun selectedTabSurvivesActivityRecreation() {
        compose.onNodeWithTag("nav-activity").performClick()
        compose.onNodeWithTag("screen-activity").assertExists()
        compose.activityRule.scenario.recreate()
        compose.waitForIdle()
        compose.onNodeWithTag("screen-activity").assertExists()
        compose.onNodeWithTag("connection-status").assertExists()
    }
}
