package io.github.mikeyphw.skybind

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.core.app.ActivityScenario
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/** Real UI assertions must run from the separately built Android test APK. */
@RunWith(AndroidJUnit4::class)
class ScaffoldTest {
    @Test fun appStartsWithoutBrokerOrRoot() {
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            scenario.onActivity { activity ->
                assertEquals("io.github.mikeyphw.skybind", activity.packageName)
                assertNotNull(activity.window.decorView)
            }
        }
    }
}
