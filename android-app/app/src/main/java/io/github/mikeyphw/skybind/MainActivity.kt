package io.github.mikeyphw.skybind

import android.content.Intent
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.delay
import io.github.mikeyphw.skybind.bridge.R1PMBridgeAgent
import io.github.mikeyphw.skybind.bridge.R1AuthorityService
import io.github.mikeyphw.skybind.bridge.SkybindSessionViewModel
import io.github.mikeyphw.skybind.ui.SkybindApp

/** UI runs unprivileged. A visible, explicit foreground session is required
 * for background PackageManager authority when switching to BKX.
 */
class MainActivity : ComponentActivity() {
    private val session: SkybindSessionViewModel by viewModels()
    private var bkxObserved by mutableStateOf(false)
    private var bkxPeerConnected by mutableStateOf(false)
    private var bkxStartFailed by mutableStateOf(false)
    private var bkxKeepBackground by mutableStateOf(true)
    private var bkxStartingSince by mutableStateOf(0L)

    override fun onStart() {
        super.onStart()
        bkxObserved = R1AuthorityService.isRunning
        bkxKeepBackground = getSharedPreferences("skybind_native", 0)
            .getBoolean("bkx_keep_background", true)
        session.onForeground()
        // Preserve the original seven-case PM bridge test behavior while UI
        // is foreground, but don't shut down a user-enabled FGS on app switch.
        R1PMBridgeAgent.start(applicationContext)
    }

    override fun onStop() {
        session.onBackground()
        if (!bkxKeepBackground && R1AuthorityService.isRunning) disableAuthority()
        if (!R1AuthorityService.isRunning) R1PMBridgeAgent.stop()
        super.onStop()
    }

    private fun updateBkxBackgroundPreference(keep: Boolean) {
        bkxKeepBackground = keep
        getSharedPreferences("skybind_native", 0).edit()
            .putBoolean("bkx_keep_background", keep).apply()
    }

    private fun enableAuthority() {
        // User gesture only. Neither root binding nor refresh may start BKX authority.
        bkxStartFailed = false
        bkxStartingSince = android.os.SystemClock.elapsedRealtime()
        val intent = Intent(this, R1AuthorityService::class.java).setAction(R1AuthorityService.ACTION_START)
        try {
            if (Build.VERSION.SDK_INT >= 26) startForegroundService(intent) else startService(intent)
        } catch (_: RuntimeException) {
            bkxStartFailed = true
            bkxStartingSince = 0L
        }
    }

    private fun disableAuthority() {
        bkxStartingSince = 0L
        try { startService(Intent(this, R1AuthorityService::class.java).setAction(R1AuthorityService.ACTION_STOP)) }
        catch (_: RuntimeException) { bkxStartFailed = true }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // The BKX foreground-service control lives in More, within MaterialTheme.
        // No unthemed strip can overlap the Android status bar on API 35/36.
        @Suppress("DEPRECATION")
        window.statusBarColor = android.graphics.Color.rgb(23, 23, 26)
        @Suppress("DEPRECATION")
        window.navigationBarColor = android.graphics.Color.BLACK
        @Suppress("DEPRECATION")
        window.decorView.systemUiVisibility = 0
        setContent {
            LaunchedEffect(Unit) {
                while (true) {
                    bkxObserved = R1AuthorityService.isRunning
                    bkxPeerConnected = R1PMBridgeAgent.peerConnected
                    if (bkxObserved) bkxStartingSince = 0L
                    if (!bkxObserved && bkxStartingSince > 0L &&
                        android.os.SystemClock.elapsedRealtime() - bkxStartingSince > 7_000L) {
                        bkxStartFailed = true
                        bkxStartingSince = 0L
                    }
                    delay(1_000L)
                }
            }
            SkybindApp(snapshot = session.snapshot,
                onRefresh = session::refresh,
                onConnect = session::connect,
                onDisconnect = session::disconnect,
                autoConnectEnabled = session.autoConnectEnabled,
                onAutoConnectChanged = session::updateAutoConnectPreference,
                bkxAuthorityRunning = bkxObserved,
                bkxPeerConnected = bkxPeerConnected,
                bkxStarting = bkxStartingSince > 0L,
                bkxStartFailed = bkxStartFailed,
                bkxKeepBackground = bkxKeepBackground,
                onBkxKeepBackgroundChanged = ::updateBkxBackgroundPreference,
                onEnableBkx = ::enableAuthority,
                onDisableBkx = ::disableAuthority,
                mountConfigMode = session.mountConfigMode,
                mountConfigDraft = session.mountConfigDraft,
                mountConfigPreview = session.configPreview,
                mountConfigBusy = session.configBusy,
                mountConfigError = session.configError,
                mountConfigFieldErrors = session.configFieldErrors,
                rollbackPreview = session.rollbackPreview,
                rollbackBusy = session.rollbackBusy,
                rollbackError = session.rollbackError,
                onPreviewRollback = session::previewRegistryRollback,
                onConfirmRollback = session::confirmRegistryRollback,
                onDismissRollback = session::dismissRegistryRollback,
                onOpenMountConfig = session::openMountEditor,
                onUpdateMountConfig = session::updateMountDraft,
                onPreviewMountConfig = session::previewMountConfig,
                onApplyMountConfig = session::applyMountConfig,
                onDismissMountConfig = session::dismissMountEditor,
                mountPreview = session.preparedMount,
                mountBusy = session.mountActionBusy,
                mountError = session.mountActionError,
                onPreviewMount = session::previewMount,
                onConfirmMount = session::confirmPreparedMount,
                onDismissMount = session::dismissMountPreview,
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
