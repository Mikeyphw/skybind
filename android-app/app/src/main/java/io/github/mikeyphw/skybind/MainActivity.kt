package io.github.mikeyphw.skybind

import android.content.Intent
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import io.github.mikeyphw.skybind.bridge.R1PMBridgeAgent
import io.github.mikeyphw.skybind.bridge.R1AuthorityService
import io.github.mikeyphw.skybind.bridge.SkybindSessionViewModel
import io.github.mikeyphw.skybind.ui.SkybindApp

/** UI runs unprivileged. A visible, explicit foreground session is required
 * for background PackageManager authority when switching to BKX.
 */
class MainActivity : ComponentActivity() {
    private val session: SkybindSessionViewModel by viewModels()
    private var authorityRunning by mutableStateOf(false)

    override fun onStart() {
        super.onStart()
        authorityRunning = R1AuthorityService.isRunning
        // Preserve the original seven-case PM bridge test behavior while UI
        // is foreground, but don't shut down a user-enabled FGS on app switch.
        R1PMBridgeAgent.start(applicationContext)
    }

    override fun onStop() {
        if (!R1AuthorityService.isRunning) R1PMBridgeAgent.stop()
        super.onStop()
    }

    private fun enableAuthority() {
        val intent = Intent(this, R1AuthorityService::class.java).setAction(R1AuthorityService.ACTION_START)
        if (Build.VERSION.SDK_INT >= 26) startForegroundService(intent) else startService(intent)
        authorityRunning = true // "requested"; actual authentication is checked by root gateway
    }

    private fun disableAuthority() {
        startService(Intent(this, R1AuthorityService::class.java).setAction(R1AuthorityService.ACTION_STOP))
        authorityRunning = false
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            Column {
                Row(Modifier.fillMaxWidth().padding(horizontal = 10.dp, vertical = 3.dp),
                    horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(if (authorityRunning) "R1 authority requested" else "R1 background authority off")
                    if (authorityRunning) {
                        OutlinedButton(onClick = ::disableAuthority) { Text("Stop bridge") }
                    } else {
                        Button(onClick = ::enableAuthority) { Text("Enable BKX bridge") }
                    }
                }
                Box(Modifier.weight(1f)) {
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
    }
}
