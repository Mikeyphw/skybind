package io.github.mikeyphw.skybind

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

/** Pre-connection UI. No Android app process can access Skybind until R1 is
 * independently authenticated; this scaffold never guesses a root socket. */
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { SkybindShell() }
    }
}

data class DeviceCapability(val name: String, val ready: Boolean)

@Composable
fun SkybindShell() {
    var selected by remember { mutableStateOf("Home") }
    val tabs = listOf("Home", "Browser", "Jobs", "Activity", "Settings")
    MaterialTheme {
        Scaffold(
            topBar = { Surface { Text("Skybind · Development", modifier = Modifier.padding(18.dp), style = MaterialTheme.typography.titleLarge) } },
            bottomBar = {
                NavigationBar {
                    tabs.forEach { tab ->
                        NavigationBarItem(
                            selected = selected == tab,
                            onClick = { selected = tab },
                            icon = { Text("•") },
                            label = { Text(tab) }
                        )
                    }
                }
            }
        ) { padding ->
            Column(Modifier.fillMaxSize().padding(padding).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(selected, style = MaterialTheme.typography.headlineMedium)
                when (selected) {
                    "Home" -> {
                        Text("Not connected: authenticated Skybind broker not yet qualified")
                        Text("No permissions or root access are requested by this build.")
                    }
                    "Browser" -> Text("Read-only remote browser unavailable until R1/R2 grants and metadata work.")
                    "Jobs" -> {
                        Text("Actionable transfers and lifecycle controls")
                        Text("No active jobs. Operations remain disabled until the broker is authenticated.")
                    }
                    "Activity" -> {
                        Text("Chronological event history (read-only)")
                        Text("No events observed. This screen does not duplicate the Jobs queue.")
                    }
                    else -> {
                        Text("Connection: not established")
                        Text("Build channel: GitHub Actions only")
                    }
                }
            }
        }
    }
}
