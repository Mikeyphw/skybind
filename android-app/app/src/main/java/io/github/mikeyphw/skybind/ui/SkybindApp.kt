package io.github.mikeyphw.skybind.ui

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import io.github.mikeyphw.skybind.model.*

private enum class Tab(val label: String, val symbol: String) {
    HOME("Home", "⌂"), BROWSER("Browser", "⌕"), JOBS("Jobs", "▤"),
    ACTIVITY("Activity", "◷"), MORE("More", "☰"),
}

@Composable
fun SkybindApp(snapshot: SkybindReadSnapshot, onRefresh: () -> Unit) {
    var selected by rememberSaveable { mutableStateOf(Tab.HOME.name) }
    val tab = Tab.entries.firstOrNull { it.name == selected } ?: Tab.HOME
    val safe = snapshot.failClosed()
    val dark = isSystemInDarkTheme()
    val context = LocalContext.current
    val scheme = if (Build.VERSION.SDK_INT >= 31) {
        if (dark) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
    } else if (dark) darkColorScheme() else lightColorScheme()
    MaterialTheme(colorScheme = scheme) {
        Scaffold(
            topBar = {
                Surface(tonalElevation = 3.dp) {
                    Row(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 14.dp),
                        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
                        Column {
                            Text("Skybind", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                            Text("Android control center", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        TextButton(onClick = onRefresh, modifier = Modifier.testTag("action-refresh")) { Text("Refresh") }
                    }
                }
            },
            bottomBar = {
                NavigationBar {
                    Tab.entries.forEach { entry ->
                        NavigationBarItem(
                            selected = tab == entry,
                            onClick = { selected = entry.name },
                            icon = { Text(entry.symbol, style = MaterialTheme.typography.titleLarge) },
                            label = { Text(entry.label, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                            modifier = Modifier.testTag("nav-" + entry.label.lowercase()),
                        )
                    }
                }
            },
        ) { inner ->
            when (tab) {
                Tab.HOME -> HomePage(safe, Modifier.padding(inner)) { selected = it.name }
                Tab.BROWSER -> BrowserPage(safe, Modifier.padding(inner))
                Tab.JOBS -> JobsPage(safe, Modifier.padding(inner)) { selected = Tab.ACTIVITY.name }
                Tab.ACTIVITY -> ActivityPage(safe, Modifier.padding(inner)) { selected = Tab.JOBS.name }
                Tab.MORE -> MorePage(safe, Modifier.padding(inner))
            }
        }
    }
}

@Composable private fun Page(title: String, subtitle: String, modifier: Modifier = Modifier, body: @Composable ColumnScope.() -> Unit) {
    LazyColumn(
        modifier = modifier.fillMaxSize().testTag("screen-" + title.lowercase()),
        contentPadding = PaddingValues(horizontal = 18.dp, vertical = 20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(title, style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.SemiBold)
                Text(subtitle, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        item { Column(verticalArrangement = Arrangement.spacedBy(12.dp), content = body) }
    }
}

@Composable private fun InfoPanel(title: String, detail: String, modifier: Modifier = Modifier, badge: String? = null) {
    ElevatedCard(modifier.fillMaxWidth(), shape = RoundedCornerShape(20.dp)) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                if (badge != null) Text(badge, color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.labelMedium)
            }
            Text(detail, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable private fun ConnectionPanel(s: SkybindReadSnapshot) {
    val label = when (s.link) {
        LinkState.ONLINE -> "Connected"
        LinkState.NOT_AUTHORIZED -> "Not authorized"
        LinkState.CONNECTING -> "Connecting"
        LinkState.DEGRADED -> "Connection degraded"
        LinkState.UNSUPPORTED -> "Unsupported API"
        LinkState.DISCONNECTED -> "Offline"
    }
    InfoPanel("Connection", s.detail, Modifier.testTag("connection-status"), label)
}

@Composable private fun HomePage(s: SkybindReadSnapshot, modifier: Modifier, select: (Tab) -> Unit) {
    Page("Home", "Your Skybind service at a glance", modifier) {
        ConnectionPanel(s)
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            InfoPanel("Remotes", if (s.online) "${s.remotes.size} configured" else "Unavailable", Modifier.weight(1f))
            InfoPanel("Jobs", if (s.online) "${s.activeJobs.size} active" else "Unavailable", Modifier.weight(1f))
        }
        InfoPanel("Mounts", if (s.online) "${s.mounts.size} known" else "No authenticated mount status")
        Text("Quick access", style = MaterialTheme.typography.titleMedium)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = { select(Tab.BROWSER) }, modifier = Modifier.testTag("home-open-browser")) { Text("Browse") }
            OutlinedButton(onClick = { select(Tab.JOBS) }, modifier = Modifier.testTag("home-open-jobs")) { Text("Jobs") }
        }
        if (!s.online) InfoPanel("Protected by default", "No root permission, remote credentials or write capabilities are requested by this development build.")
    }
}

@Composable private fun BrowserPage(s: SkybindReadSnapshot, modifier: Modifier) {
    var search by rememberSaveable { mutableStateOf("") }
    Page("Browser", "Explore configured remotes without mounting", modifier) {
        ConnectionPanel(s)
        OutlinedTextField(value = search, onValueChange = { search = it }, label = { Text("Search remotes") },
            singleLine = true, enabled = s.online, modifier = Modifier.fillMaxWidth().testTag("browser-search"))
        if (!s.online) {
            InfoPanel("Remote browser unavailable", "Authenticate the Skybind broker to browse. Existing remotes and credentials are never copied into this app.")
        } else {
            val filtered = s.remotes.filter { it.displayName.contains(search.trim(), ignoreCase = true) }
            if (filtered.isEmpty()) InfoPanel("No matching remotes", "Change the search or configure a remote through a qualified backend.")
            filtered.take(64).forEach { remote ->
                InfoPanel(remote.displayName, "${remote.kind} · Folder listing requires the read-only metadata capability", Modifier.testTag("remote-${remote.id}"))
            }
        }
        Button(onClick = {}, enabled = false, modifier = Modifier.testTag("browser-write-disabled")) { Text("Transfer · requires authorized preview") }
    }
}

@Composable private fun JobsPage(s: SkybindReadSnapshot, modifier: Modifier, openActivity: () -> Unit) {
    Page("Jobs", "Active and actionable work · server-authoritative", modifier) {
        ConnectionPanel(s)
        Text("Current operations", style = MaterialTheme.typography.titleMedium)
        if (!s.online) InfoPanel("Job queue unavailable", "The app cannot safely observe or cancel jobs until connected.")
        else if (s.activeJobs.isEmpty()) InfoPanel("Nothing running", "Queued, running and interrupted work appears here.")
        s.activeJobs.take(32).forEach { job -> JobCard(job, false) }
        Text("Recent completed", style = MaterialTheme.typography.titleMedium)
        if (s.online && s.recentJobs.isEmpty()) Text("No recently finished jobs", style = MaterialTheme.typography.bodyMedium)
        s.recentJobs.take(10).forEach { job -> JobCard(job, true) }
        TextButton(onClick = openActivity, modifier = Modifier.testTag("jobs-view-activity")) { Text("View chronological activity →") }
    }
}

@Composable private fun JobCard(job: JobSummary, finished: Boolean) {
    ElevatedCard(Modifier.fillMaxWidth().testTag("job-${job.id}")) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(job.title, style = MaterialTheme.typography.titleMedium)
                Text(job.state.name.lowercase().replaceFirstChar { it.uppercase() }, style = MaterialTheme.typography.labelMedium)
            }
            if (job.totalBytes != null && job.totalBytes > 0) {
                val ratio = (job.transferredBytes.toFloat() / job.totalBytes).coerceIn(0f, 1f)
                LinearProgressIndicator(progress = { ratio }, modifier = Modifier.fillMaxWidth())
            } else if (!finished) Text("Progress total unknown", style = MaterialTheme.typography.bodySmall)
            Text("ID: ${job.id}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            // Cancellation is disabled until verified broker ownership + exact job ID.
            if (!finished) TextButton(onClick = {}, enabled = false, modifier = Modifier.testTag("cancel-${job.id}")) { Text("Cancel · authorization required") }
        }
    }
}

@Composable private fun ActivityPage(s: SkybindReadSnapshot, modifier: Modifier, openJobs: () -> Unit) {
    var onlyWarnings by rememberSaveable { mutableStateOf(false) }
    Page("Activity", "Read-only chronological journal · not the job queue", modifier) {
        ConnectionPanel(s)
        if (s.hasEventGap) InfoPanel("Journal gap", "Some events could not be replayed. Reload from the authoritative daemon snapshot.")
        FilterChip(selected = onlyWarnings, onClick = { onlyWarnings = !onlyWarnings },
            label = { Text("Warnings and errors") }, modifier = Modifier.testTag("activity-filter-warnings"))
        if (!s.online) InfoPanel("No authenticated journal", "Connection is required for event cursor/replay. No historical records are invented.")
        else {
            val filtered = s.timeline.filter { !onlyWarnings || it.severity != ActivitySeverity.INFO }
            if (filtered.isEmpty()) InfoPanel("No events", "The selected activity filter has no entries.")
            filtered.take(100).forEach { event ->
                ElevatedCard(Modifier.fillMaxWidth().testTag("event-${event.sequence}")) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                        Text(event.title, style = MaterialTheme.typography.titleSmall)
                        Text("${event.occurredAt} · ${event.severity.name} · #${event.sequence}", style = MaterialTheme.typography.labelSmall)
                        if (event.operationId != null) Text("Job ID: ${event.operationId}", style = MaterialTheme.typography.labelSmall)
                    }
                }
            }
        }
        TextButton(onClick = openJobs, modifier = Modifier.testTag("activity-view-jobs")) { Text("Open actionable Jobs →") }
    }
}

@Composable private fun MorePage(s: SkybindReadSnapshot, modifier: Modifier) {
    Page("More", "Preferences and available capabilities", modifier) {
        ConnectionPanel(s)
        InfoPanel("Skybind backend", s.serverVersion ?: "Version unavailable until authenticated")
        InfoPanel("Mount control", if (s.online) "${s.mounts.size} mounts discovered; management remains disabled" else "Waiting for a secure read-only connection")
        if (s.online) s.mounts.take(20).forEach { mount ->
            InfoPanel(mount.displayName, "Status: ${mount.state}", Modifier.testTag("mount-${mount.id}"))
        }
        InfoPanel("Permissions", "No root, storage-wide, exported broker, or general command permission granted.")
        InfoPanel("Native app", "Development build · Android API ${Build.VERSION.SDK_INT}")
        Button(onClick = {}, enabled = false, modifier = Modifier.testTag("more-mount-control-disabled")) { Text("Manage mounts · unavailable") }
    }
}
