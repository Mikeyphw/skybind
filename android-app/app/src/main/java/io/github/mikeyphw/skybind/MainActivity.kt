package io.github.mikeyphw.skybind

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import io.github.mikeyphw.skybind.bridge.SkybindSessionViewModel
import io.github.mikeyphw.skybind.bridge.R1PMBridgeAgent
import io.github.mikeyphw.skybind.ui.SkybindApp

/** Unprivileged UI: no su commands, socket paths, or embedded daemon. */
class MainActivity : ComponentActivity() {
    private val session: SkybindSessionViewModel by viewModels()
    override fun onStart() {
        super.onStart()
        R1PMBridgeAgent.start(applicationContext)
    }

    override fun onStop() {
        R1PMBridgeAgent.stop()
        super.onStop()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            SkybindApp(snapshot = session.snapshot,
                onRefresh = session::refresh,
                onConnect = session::connect,
                onDisconnect = session::disconnect,
                browser = session.browser,
                onBrowseRemote = session::selectRemote,
                onBrowseFolder = session::openFolder,
                onBrowseUp = session::parentFolder,
                onSwitchRemote = session::switchRemote,
                jobPreview = session.preparedJob,
                jobBusy = session.jobActionBusy,
                jobError = session.jobActionError,
                ownedRunIds = session.ownedRunIds,
                onPreviewJob = session::previewJob,
                onConfirmJob = session::confirmPreparedJob,
                onDismissJob = session::dismissJobPreview,
                onCancelOwnedRun = session::cancelOwnedRun)
        }
    }
}
