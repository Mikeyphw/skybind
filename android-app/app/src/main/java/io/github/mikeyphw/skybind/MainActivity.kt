package io.github.mikeyphw.skybind

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.*
import io.github.mikeyphw.skybind.model.*
import io.github.mikeyphw.skybind.ui.SkybindApp

/** Android application process is unprivileged. The native UI never runs su. */
class MainActivity : ComponentActivity() {
    private val coordinator = ReadOnlyCoordinator(UnpairedGateway())

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            var refreshNumber by remember { mutableIntStateOf(0) }
            var snapshot by remember { mutableStateOf(SkybindReadSnapshot(LinkState.CONNECTING, "Checking the connection")) }
            LaunchedEffect(refreshNumber) { snapshot = coordinator.refresh() }
            SkybindApp(snapshot = snapshot, onRefresh = { refreshNumber += 1 })
        }
    }
}
