package io.github.mikeyphw.skybind

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import io.github.mikeyphw.skybind.bridge.SkybindSessionViewModel
import io.github.mikeyphw.skybind.ui.SkybindApp

/** Unprivileged UI: no su commands, socket paths, or embedded daemon. */
class MainActivity : ComponentActivity() {
    private val session: SkybindSessionViewModel by viewModels()
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            SkybindApp(snapshot = session.snapshot,
                onRefresh = session::refresh,
                onConnect = session::connect,
                browser = session.browser,
                onBrowseRemote = session::selectRemote,
                onBrowseFolder = session::openFolder,
                onBrowseUp = session::parentFolder,
                onSwitchRemote = session::switchRemote)
        }
    }
}
