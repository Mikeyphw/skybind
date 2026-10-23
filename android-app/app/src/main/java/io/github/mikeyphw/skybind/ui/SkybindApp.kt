package io.github.mikeyphw.skybind.ui

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.clickable
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import io.github.mikeyphw.skybind.model.*

private enum class Tab(val label: String, val symbol: String) {
    HOME("Home", "⌂"), MOUNTS("Mounts", "▥"), BROWSER("Browser", "⌕"),
    JOBS("Jobs", "▤"), MORE("More", "☰"),
}

@Composable
fun SkybindApp(snapshot: SkybindReadSnapshot, onRefresh: () -> Unit, onConnect: () -> Unit = {},
    onDisconnect: () -> Unit = {},
    autoConnectEnabled: Boolean = true, onAutoConnectChanged: (Boolean) -> Unit = {},
    bkxAuthorityRunning: Boolean = false, bkxPeerConnected: Boolean = false,
    bkxStarting: Boolean = false, bkxStartFailed: Boolean = false,
    bkxKeepBackground: Boolean = true, onBkxKeepBackgroundChanged: (Boolean) -> Unit = {},
    onEnableBkx: () -> Unit = {},
    onDisableBkx: () -> Unit = {},
    mountConfigMode: String? = null, mountConfigDraft: MountDraft? = null,
    mountConfigPreview: PreparedConfigChange? = null, mountConfigBusy: Boolean = false,
    mountConfigError: String? = null,
    mountConfigFieldErrors: Map<String, String> = emptyMap(),
    rollbackPreview: PreparedRegistryRollback? = null,
    rollbackBusy: Boolean = false,
    rollbackError: String? = null,
    onPreviewRollback: () -> Unit = {},
    onConfirmRollback: () -> Unit = {},
    onDismissRollback: () -> Unit = {},
    onOpenMountConfig: (String, String) -> Unit = { _, _ -> },
    onUpdateMountConfig: (MountDraft) -> Unit = {},
    onPreviewMountConfig: () -> Unit = {}, onApplyMountConfig: () -> Unit = {},
    onDismissMountConfig: () -> Unit = {},
    mountPreview: PreparedMountAction? = null, mountBusy: Boolean = false,
    mountError: String? = null, onPreviewMount: (String, String) -> Unit = { _, _ -> },
    onConfirmMount: () -> Unit = {}, onDismissMount: () -> Unit = {},
    browser: BrowserState = BrowserState(), onBrowseRemote: (String) -> Unit = {},
    onBrowseFolder: (String) -> Unit = {}, onBrowseUp: () -> Unit = {},
    onSwitchRemote: () -> Unit = {},
    jobPreview: PreparedJob? = null, jobBusy: Boolean = false,
    jobError: String? = null, ownedRunIds: Set<String> = emptySet(),
    onPreviewJob: (String) -> Unit = {}, onConfirmJob: () -> Unit = {},
    onDismissJob: () -> Unit = {}, onCancelOwnedRun: (String) -> Unit = {}) {
    var selected by rememberSaveable { mutableStateOf(Tab.HOME.name) }
    var remoteSearch by rememberSaveable { mutableStateOf("") }
    // Hoisted across tab changes/recreation; folder identity resets scroll explicitly.
    val browserScroll = rememberLazyListState()
    var activityFromJobs by rememberSaveable { mutableStateOf(false) }
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
                            Text("Filesystem Control", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
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
                            modifier = Modifier.testTag("nav-" + entry.label.lowercase()).semantics {
                                contentDescription = "${entry.label} tab"
                            },
                        )
                    }
                }
            },
        ) { inner ->
            when (tab) {
                Tab.HOME -> HomePage(safe, Modifier.padding(inner), onConnect, onDisconnect) { selected = it.name }
                Tab.MOUNTS -> MountsPage(safe, Modifier.padding(inner), mountBusy || mountConfigBusy || rollbackBusy,
                    mountError ?: mountConfigError ?: rollbackError, onPreviewMount, onOpenMountConfig, onPreviewRollback)
                Tab.BROWSER -> BrowserPage(safe, browser.forSnapshot(safe), Modifier.padding(inner),
                    onBrowseRemote, onBrowseFolder, onBrowseUp, onSwitchRemote,
                    browserScroll, remoteSearch, { remoteSearch = it })
                Tab.JOBS -> JobsPage(safe, Modifier.padding(inner), ownedRunIds, jobBusy,
                    jobError, onPreviewJob, onCancelOwnedRun) { activityFromJobs = true; selected = Tab.MORE.name }
                Tab.MORE -> MorePage(safe, Modifier.padding(inner), onConnect, onDisconnect,
                    autoConnectEnabled, onAutoConnectChanged, bkxAuthorityRunning,
                    bkxPeerConnected, bkxStarting, bkxStartFailed, bkxKeepBackground,
                    onBkxKeepBackgroundChanged, onEnableBkx, onDisableBkx, activityFromJobs, {
                        if (!it && activityFromJobs) selected = Tab.JOBS.name
                        activityFromJobs = it
                    })
            }
        }
        if (mountConfigMode != null && mountConfigDraft != null && safe.online) {
            MountConfigEditor(mountConfigMode, if (mountConfigMode == "create") "" else mountConfigDraft.name,
                mountConfigDraft, safe.remotes.map { it.id }, mountConfigPreview, mountConfigBusy, mountConfigError,
                mountConfigFieldErrors, onUpdateMountConfig, onPreviewMountConfig, onApplyMountConfig, onDismissMountConfig)
        }
        if (rollbackPreview != null && safe.online) {
            var approved by remember(rollbackPreview.id) { mutableStateOf(false) }
            AlertDialog(onDismissRequest = onDismissRollback,
                title = { Text("Restore previous mount configuration") },
                text = {
                    Column(Modifier.heightIn(max = 380.dp).verticalScroll(rememberScrollState()),
                        verticalArrangement = Arrangement.spacedBy(9.dp)) {
                        Text("This restores the ENTIRE registry, not just one mount. Any affected active mount may be stopped or restarted by the daemon.")
                        Text("Revision: ${rollbackPreview.baseRevision} · expires in 60 seconds")
                        rollbackPreview.effects.forEach { Text("Effect: $it") }
                        Text("The daemon performs ownership and pending-write checks. A failed or ambiguous response must be inspected before another attempt.")
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Checkbox(checked = approved, onCheckedChange = { approved = it },
                                modifier = Modifier.testTag("rollback-consent"))
                            Text("I approve restoring the full previous configuration")
                        }
                    }
                },
                confirmButton = {
                    Button(onClick = onConfirmRollback, enabled = approved && !rollbackBusy,
                        modifier = Modifier.testTag("rollback-confirm")) { Text("Restore") }
                },
                dismissButton = {
                    TextButton(onClick = onDismissRollback, modifier = Modifier.testTag("rollback-cancel")) { Text("Cancel") }
                }, modifier = Modifier.testTag("rollback-review"))
        }
        if (mountPreview != null && safe.online) {
            var acknowledged by remember(mountPreview.id) { mutableStateOf(false) }
            val action = mountPreview.action
            AlertDialog(
                onDismissRequest = onDismissMount,
                title = { Text("Confirm mount ${action.replaceFirstChar { it.uppercase() }}") },
                text = {
                    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text(if (action == "reconcile")
                            "Reconcile all ${mountPreview.configuredCount} configured mounts"
                            else "Mount: ${mountPreview.name}")
                        if (action == "start") {
                            Text("Remote: ${mountPreview.remote}", style = MaterialTheme.typography.bodySmall)
                            Text("Destination: ${mountPreview.mountpoint}", style = MaterialTheme.typography.bodySmall)
                            Text("Daemon validates a one-use, revision-bound start proof.")
                        } else if (action == "reconcile") {
                            Text("May start desired mounts and update recovery state across all mounts.")
                        } else {
                            Text("Observed: ${mountPreview.observed}; desired: ${mountPreview.desired}")
                            Text("Stopping or restarting can disrupt open files. The daemon enforces FUSE ownership and safe-stop rules.")
                        }
                        Text("Confirmation expires in 60 seconds. Transport failure is ambiguous; never retry automatically.")
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Checkbox(checked = acknowledged, onCheckedChange = { acknowledged = it },
                                modifier = Modifier.testTag("mount-action-consent"))
                            Text("I authorize this mount operation.")
                        }
                    }
                },
                confirmButton = {
                    Button(onClick = onConfirmMount, enabled = !mountBusy && acknowledged,
                        modifier = Modifier.testTag("mount-action-confirm")) { Text("Execute") }
                },
                dismissButton = {
                    TextButton(onClick = onDismissMount, modifier = Modifier.testTag("mount-action-dismiss")) { Text("Cancel") }
                },
                modifier = Modifier.testTag("mount-action-dialog"),
            )
        }
        if (jobPreview != null && safe.online) {
            var confirmedCopy by remember(jobPreview.id) { mutableStateOf(false) }
            AlertDialog(
                onDismissRequest = onDismissJob,
                title = { Text("Confirm scheduled job") },
                text = {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("${jobPreview.name} · ${jobPreview.kind.uppercase()}")
                        Text("From: ${jobPreview.source}", style = MaterialTheme.typography.bodySmall)
                        Text("To: ${jobPreview.destination}", style = MaterialTheme.typography.bodySmall)
                        Text("Preview expires shortly. The daemon rechecks a one-use proof.")
                        if (jobPreview.kind == "copy") {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Checkbox(checked = confirmedCopy,
                                    onCheckedChange = { confirmedCopy = it },
                                    modifier = Modifier.testTag("job-copy-consent"))
                                Text("I authorize this copy job, including destination writes.")
                            }
                        }
                    }
                },
                confirmButton = {
                    Button(onClick = onConfirmJob, enabled = !jobBusy &&
                        (jobPreview.kind == "check" || confirmedCopy),
                        modifier = Modifier.testTag("job-confirm-start")) { Text("Start job") }
                },
                dismissButton = {
                    TextButton(onClick = onDismissJob, modifier = Modifier.testTag("job-dismiss-preview")) {
                        Text("Cancel")
                    }
                },
                modifier = Modifier.testTag("job-confirm-dialog"),
            )
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

@Composable private fun HomePage(s: SkybindReadSnapshot, modifier: Modifier, onConnect: () -> Unit,
    onDisconnect: () -> Unit, select: (Tab) -> Unit) {
    Page("Home", "Your Skybind service at a glance", modifier) {
        ConnectionPanel(s)
        if (s.link == LinkState.NOT_AUTHORIZED || s.link == LinkState.DISCONNECTED) {
            Button(onClick = onConnect, modifier = Modifier.testTag("connect-readonly")) {
                Text("Retry root connection")
            }
        } else if (s.link == LinkState.ONLINE || s.link == LinkState.DEGRADED) {
            // Unbind only this app-owned session; do NOT revoke the root grant or stop the daemon.
            OutlinedButton(onClick = onDisconnect, modifier = Modifier.testTag("disconnect-readonly")) {
                Text("Disconnect")
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            InfoPanel("Remotes", if (s.online) "${s.remotes.size} configured" else "Unavailable", Modifier.weight(1f))
            InfoPanel("Jobs", if (s.online) "${s.activeJobs.size} active" else "Unavailable", Modifier.weight(1f))
        }
        InfoPanel("Runtime integrity", if (s.online) {
            when {
                s.runtime == null -> "Unverified · no runtime evidence"
                s.runtime.ready && s.runtime.provenanceValid ->
                    "On-disk runtime verified · ${s.runtime.provider}; FUSE availability not implied"
                else -> "Runtime not verified · check daemon/module diagnostics"
            }
        } else "Unavailable while disconnected", Modifier.testTag("home-runtime-health"))
        InfoPanel("Mounts", if (s.online) "${s.mounts.size} configured · ${s.mounts.count { it.state == "RUNNING" }} running" +
            (if (s.mounts.any { it.state == "DEGRADED" || it.state == "MOUNT_STALE" }) " · attention needed" else "")
            else "Mount status unavailable until connected", Modifier.testTag("home-mount-summary"))
        InfoPanel("Network (Android)", NativePresentation.androidNetwork(LocalContext.current) +
            " · does not prove daemon/provider connectivity", Modifier.testTag("home-network"))
        Text("Quick access", style = MaterialTheme.typography.titleMedium)
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = { select(Tab.MOUNTS) }, modifier = Modifier.testTag("home-open-mounts")) { Text("Mounts") }
            OutlinedButton(onClick = { select(Tab.BROWSER) }, modifier = Modifier.testTag("home-open-browser")) { Text("Browse") }
            OutlinedButton(onClick = { select(Tab.JOBS) }, modifier = Modifier.testTag("home-open-jobs")) { Text("Jobs") }
        }
        if (!s.online) InfoPanel("Root access", "Skybind connects automatically in the foreground. Approval is controlled by your root manager; no mount or job action starts automatically.")
    }
}

@Composable private fun MountsPage(s: SkybindReadSnapshot, modifier: Modifier,
    busy: Boolean, error: String?, preview: (String, String) -> Unit,
    editConfig: (String, String) -> Unit, rollback: () -> Unit) {
    LazyColumn(modifier.fillMaxSize().testTag("screen-mounts"),
        contentPadding = PaddingValues(horizontal = 18.dp, vertical = 20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("Mounts", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.SemiBold)
                Text("Authoritative daemon mount status", color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        item { ConnectionPanel(s) }
        if (s.online) item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = { editConfig("create", "") }, enabled = !busy,
                    modifier = Modifier.testTag("mount-add")) { Text("Add mount") }
                OutlinedButton(onClick = rollback, enabled = !busy,
                    modifier = Modifier.testTag("mount-rollback")) { Text("Restore previous") }
            }
        }
        if (error != null) item { InfoPanel("Mount action not verified", error, Modifier.testTag("mount-action-error")) }
        if (busy) item { LinearProgressIndicator(Modifier.fillMaxWidth().testTag("mount-action-busy")) }
        if (!s.online) {
            item { InfoPanel("Mount status unavailable", "Authorize Skybind to inspect configured mounts.") }
        } else if (s.mounts.isEmpty()) {
            item { InfoPanel("No mounts configured", "Use Add mount to configure your first remote filesystem.") }
        } else {
            item { Row(verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                Text("${s.mounts.size} configured · ${s.mounts.count { it.state == "RUNNING" }} running")
                OutlinedButton(onClick = { preview("reconcile", "") }, enabled = !busy,
                    modifier = Modifier.testTag("mount-reconcile")) { Text("Reconcile") }
            } }
            items(s.mounts, key = { it.id }) { mount ->
                val status = when (mount.state) {
                    "RUNNING" -> "Running"
                    "STOPPED" -> "Stopped"
                    "DEGRADED" -> "Degraded"
                    "MOUNT_STALE" -> "Stale or foreign mount"
                    else -> "Unknown"
                }
                Column(Modifier.fillMaxWidth().testTag("mount-${mount.id}"),
                    verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    InfoPanel(mount.displayName,
                        "${if (mount.desired) "Desired: on" else "Desired: off"}" +
                        (mount.recoveryAttempts?.let { " · recovery attempts: $it" } ?: "") +
                        (mount.recoveryClass?.let { " · $it" } ?: ""),
                        badge = status)
                    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        OutlinedButton(onClick = { editConfig("edit", mount.id) },
                            enabled = !busy, modifier = Modifier.testTag("mount-edit-${mount.id}")) { Text("Edit") }
                        TextButton(onClick = { editConfig("delete", mount.id) },
                            enabled = !busy, modifier = Modifier.testTag("mount-delete-${mount.id}")) { Text("Delete") }
                    }
                    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        OutlinedButton(onClick = { preview("start", mount.id) },
                            enabled = !busy && mount.state == "STOPPED",
                            modifier = Modifier.testTag("mount-start-${mount.id}")) { Text("Start") }
                        OutlinedButton(onClick = { preview("stop", mount.id) },
                            enabled = !busy && mount.state == "RUNNING",
                            modifier = Modifier.testTag("mount-stop-${mount.id}")) { Text("Stop") }
                        OutlinedButton(onClick = { preview("restart", mount.id) },
                            enabled = !busy && mount.state == "RUNNING",
                            modifier = Modifier.testTag("mount-restart-${mount.id}")) { Text("Restart") }
                    }
                }
            }
            item { Text("Every operation needs a fresh root-service preview and explicit confirmation. Configuration changes require daemon validation, a one-use proof, and explicit approval.",
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
        }
    }
}

@Composable private fun BrowserPage(s: SkybindReadSnapshot, browse: BrowserState, modifier: Modifier,
    onRemote: (String) -> Unit, onFolder: (String) -> Unit, onUp: () -> Unit, onSwitch: () -> Unit,
    scroll: LazyListState, search: String, onSearch: (String) -> Unit) {
    LaunchedEffect(browse.remote, browse.path) { scroll.scrollToItem(0) }
    LazyColumn(modifier.fillMaxSize().testTag("screen-browser"), state = scroll,
        contentPadding = PaddingValues(horizontal = 18.dp, vertical = 20.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("Browser", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.SemiBold)
                Text("Live remote contents · no transfers", color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        item { ConnectionPanel(s) }
        if (!s.online) {
            item { InfoPanel("Remote browser unavailable", "Connect to Skybind; credentials stay in the daemon.") }
        } else if (browse.remote == null) {
            item { OutlinedTextField(value = search, onValueChange = onSearch,
                label = { Text("Search remotes") }, singleLine = true,
                modifier = Modifier.fillMaxWidth().testTag("browser-search")) }
            val found = s.remotes.filter { it.displayName.contains(search.trim(), ignoreCase = true) }.take(64)
            if (found.isEmpty()) item { InfoPanel("No matching remotes", "Try another search term.") }
            items(found, key = { it.id }) { remote ->
                OutlinedButton(onClick = { onRemote(remote.id) },
                    modifier = Modifier.fillMaxWidth().testTag("remote-${remote.id}")) {
                    Text("${remote.displayName} · ${remote.kind}  →", maxLines = 2, overflow = TextOverflow.Ellipsis)
                }
            }
        } else {
            item { InfoPanel("Current folder", "${browse.remote}:${browse.path.ifBlank { "/" }}", Modifier.testTag("browser-path")) }
            item { Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = onUp, modifier = Modifier.testTag("browser-up")) { Text("Up") }
                TextButton(onClick = onSwitch, modifier = Modifier.testTag("browser-switch-remote")) { Text("Remotes") }
            } }
            when {
                browse.loading -> item { LinearProgressIndicator(Modifier.fillMaxWidth().testTag("browser-loading")) }
                browse.error != null -> item { InfoPanel("Listing unavailable", browse.error, Modifier.testTag("browser-error")) }
                browse.entries.isEmpty() -> item { InfoPanel("Empty folder", "Nothing to list here.") }
                else -> {
                    itemsIndexed(browse.entries.take(200), key = { _, entry -> "${browse.remote}:${browse.path}:${entry.directory}:${entry.name}" }) { _, entry ->
                        if (entry.directory) {
                            OutlinedButton(onClick = { onFolder(entry.name) },
                                modifier = Modifier.fillMaxWidth().testTag("folder-${entry.name}")) {
                                Text("📁  ${entry.name}  →", maxLines = 2, overflow = TextOverflow.Ellipsis)
                            }
                        } else {
                            ListItem(headlineContent = { Text(entry.name, maxLines = 2, overflow = TextOverflow.Ellipsis) },
                                supportingContent = { Text("File · ${NativePresentation.bytes(entry.sizeBytes)}") },
                                modifier = Modifier.testTag("file-${entry.name}"))
                        }
                    }
                    if (browse.entries.size > 200) item { Text("Showing first 200 results. Refine the folder to inspect more.") }
                }
            }
        }
        item { Button(onClick = {}, enabled = false, modifier = Modifier.testTag("browser-write-disabled")) {
            Text("Transfer · requires authorized preview")
        } }
    }
}

@Composable private fun JobsPage(s: SkybindReadSnapshot, modifier: Modifier,
    ownedRunIds: Set<String>, busy: Boolean, error: String?,
    onPreview: (String) -> Unit, onCancel: (String) -> Unit, openActivity: () -> Unit) {
    LazyColumn(modifier.fillMaxSize().testTag("screen-jobs"),
        contentPadding = PaddingValues(horizontal = 18.dp, vertical = 20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { Text("Jobs", style = MaterialTheme.typography.headlineMedium) }
        item { Text("Daemon-owned scheduled jobs and verified progress", color = MaterialTheme.colorScheme.onSurfaceVariant) }
        item { ConnectionPanel(s) }
        if (error != null) item { InfoPanel("Operation not confirmed", error, Modifier.testTag("job-action-error")) }
        if (busy) item { LinearProgressIndicator(Modifier.fillMaxWidth().testTag("job-operation-busy")) }
        item { Text("Configured jobs · ${if (s.online) s.definitions.size else 0}", style = MaterialTheme.typography.titleMedium) }
        if (!s.online) item { InfoPanel("Job queue unavailable", "Authenticate root first; no privileged job starts automatically.") }
        else if (s.definitions.isEmpty()) item { InfoPanel("No configured jobs", "Configure jobs in the management interface.") }
        if (s.online) items(s.definitions.take(64), key = { "def-${it.name}" }) { definition ->
            Row(Modifier.fillMaxWidth().heightIn(min = 56.dp), horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(definition.name, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    Text("${definition.kind.uppercase()} · ${if (definition.enabled) "enabled" else "disabled"}",
                        style = MaterialTheme.typography.bodySmall)
                }
                OutlinedButton(onClick = { onPreview(definition.name) }, enabled = !busy &&
                    definition.kind in setOf("check", "copy"),
                    modifier = Modifier.testTag("job-preview-${definition.name}").heightIn(min = 48.dp)) {
                    Text(if (definition.kind == "sync") "Sync locked" else "Preview")
                }
            }
        }
        item { Text("Current operations", style = MaterialTheme.typography.titleMedium) }
        if (s.online && s.activeJobs.isEmpty()) item { InfoPanel("Nothing running", "No queued, running or interrupted work.") }
        if (s.online) items(s.activeJobs.take(64), key = { "active-${it.id}" }) { job ->
            JobCard(job, finished = false, owned = job.id in ownedRunIds, busy = busy, onCancel = onCancel)
        }
        item { Text("Recent completed", style = MaterialTheme.typography.titleMedium) }
        if (s.online && s.recentJobs.isEmpty()) item { Text("No recently finished jobs") }
        if (s.online) items(s.recentJobs.take(64), key = { "recent-${it.id}" }) { job ->
            JobCard(job, finished = true, owned = false, busy = busy, onCancel = onCancel)
        }
        item { TextButton(onClick = openActivity, modifier = Modifier.testTag("jobs-view-activity").heightIn(min = 48.dp)) {
            Text("View chronological activity →")
        } }
    }
}

@Composable private fun JobCard(job: JobSummary, finished: Boolean, owned: Boolean,
    busy: Boolean, onCancel: (String) -> Unit) {
    ElevatedCard(Modifier.fillMaxWidth().testTag("job-${job.id}")) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(job.title, style = MaterialTheme.typography.titleMedium)
                Text(job.state.name.lowercase().replaceFirstChar { it.uppercase() },
                    style = MaterialTheme.typography.labelMedium)
            }
            if (job.totalBytes != null && job.totalBytes > 0) {
                val ratio = (job.transferredBytes.toFloat() / job.totalBytes).coerceIn(0f, 1f)
                LinearProgressIndicator(progress = { ratio }, modifier = Modifier.fillMaxWidth())
            } else if (job.percent != null) {
                LinearProgressIndicator(progress = { (job.percent / 100.0).toFloat() },
                    modifier = Modifier.fillMaxWidth())
            } else if (!finished) Text("Progress total unknown", style = MaterialTheme.typography.bodySmall)
            Text("${NativePresentation.bytes(job.transferredBytes)} transferred" +
                (job.totalBytes?.let { " / ${NativePresentation.bytes(it)}" } ?: ""),
                style = MaterialTheme.typography.bodySmall)
            if (job.speedBytesPerSecond != null) Text("${NativePresentation.bytes(job.speedBytesPerSecond.toLong())}/s",
                style = MaterialTheme.typography.bodySmall)
            if (job.etaSeconds != null) Text("ETA ${job.etaSeconds}s", style = MaterialTheme.typography.bodySmall)
            if (job.filesDone != null) Text("Files: ${job.filesDone}" +
                (job.filesTotal?.let { " / $it" } ?: ""), style = MaterialTheme.typography.bodySmall)
            var showId by remember(job.id) { mutableStateOf(false) }
            TextButton(onClick = { showId = !showId },
                modifier = Modifier.testTag("job-receipt-${job.id}").heightIn(min = 48.dp)) {
                Text(if (showId) "Hide receipt ID" else "Show receipt ID")
            }
            if (showId) Text("Run receipt: ${job.id}", style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            if (!finished) {
                TextButton(onClick = { if (owned) onCancel(job.id) },
                    enabled = owned && !busy && job.state == JobState.RUNNING,
                    modifier = Modifier.testTag("cancel-${job.id}")) {
                    Text(if (owned) "Cancel my job" else "Cancel · not owned by this session")
                }
            }
        }
    }
}

@Composable private fun ActivityPage(s: SkybindReadSnapshot, modifier: Modifier, openJobs: () -> Unit) {
    var onlyWarnings by rememberSaveable { mutableStateOf(false) }
    var onlyErrors by rememberSaveable { mutableStateOf(false) }
    val filtered = s.timeline.filter { if (onlyErrors) it.severity == ActivitySeverity.ERROR
        else !onlyWarnings || it.severity != ActivitySeverity.INFO }.take(100)
    LazyColumn(modifier.fillMaxSize().testTag("screen-activity"),
        contentPadding = PaddingValues(horizontal = 18.dp, vertical = 20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { Text("Activity", style = MaterialTheme.typography.headlineMedium) }
        item { Text("Daemon journal · newest first · last 100 verified events", color = MaterialTheme.colorScheme.onSurfaceVariant) }
        item { ConnectionPanel(s) }
        if (s.hasEventGap) item { InfoPanel("Journal gap / replay reset",
            "Some events were unavailable. Refresh the authoritative daemon snapshot; history is not reconstructed.",
            Modifier.testTag("activity-journal-gap")) }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(selected = onlyWarnings && !onlyErrors, onClick = { onlyWarnings = !onlyWarnings; onlyErrors = false },
                    label = { Text("Warnings + errors") }, modifier = Modifier.testTag("activity-filter-warnings").heightIn(min = 48.dp))
                FilterChip(selected = onlyErrors, onClick = { onlyErrors = !onlyErrors; if (onlyErrors) onlyWarnings = false },
                    label = { Text("Errors") }, modifier = Modifier.testTag("activity-filter-errors").heightIn(min = 48.dp))
            }
        }
        if (!s.online) item { InfoPanel("No authenticated journal", "Reconnect to read current event history.") }
        else if (filtered.isEmpty()) item { InfoPanel("No events", "No journal entries match this filter.") }
        if (s.online) items(filtered, key = { it.sequence }) { event ->
            var expanded by remember(event.sequence) { mutableStateOf(false) }
            ElevatedCard(Modifier.fillMaxWidth().testTag("event-${event.sequence}")) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                    Text(NativePresentation.label(event.title), style = MaterialTheme.typography.titleSmall)
                    Text("${NativePresentation.time(event.occurredAt)} · ${event.severity.name}",
                        color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.labelMedium)
                    TextButton(onClick = { expanded = !expanded },
                        modifier = Modifier.testTag("activity-details-${event.sequence}").heightIn(min = 48.dp)) {
                        Text(if (expanded) "Hide technical details" else "Technical details")
                    }
                    if (expanded) {
                        Text("Event #${event.sequence} · ${event.title}", style = MaterialTheme.typography.bodySmall)
                        if (event.operationId != null) Text("Operation receipt: ${event.operationId}",
                            style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
        }
        item { TextButton(onClick = openJobs, modifier = Modifier.testTag("activity-view-jobs").heightIn(min = 48.dp)) {
            Text("Open actionable Jobs →")
        } }
    }
}

@Composable private fun MorePage(s: SkybindReadSnapshot, modifier: Modifier,
    onConnect: () -> Unit, onDisconnect: () -> Unit,
    autoConnectEnabled: Boolean, onAutoConnectChanged: (Boolean) -> Unit,
    bkxAuthorityRunning: Boolean, bkxPeerConnected: Boolean, bkxStarting: Boolean,
    bkxStartFailed: Boolean, bkxKeepBackground: Boolean,
    onBkxKeepBackgroundChanged: (Boolean) -> Unit,
    onEnableBkx: () -> Unit, onDisableBkx: () -> Unit,
    showActivity: Boolean, setShowActivity: (Boolean) -> Unit) {
    if (showActivity) {
        ActivityPage(s, modifier) { setShowActivity(false) }
        return
    }
    Page("More", "Settings and diagnostics", modifier) {
        ConnectionPanel(s)
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("Auto-connect root", fontWeight = FontWeight.SemiBold)
                Text("Connect when opened; root manager still authorizes access.",
                    style = MaterialTheme.typography.bodySmall)
            }
            Switch(checked = autoConnectEnabled, onCheckedChange = onAutoConnectChanged,
                modifier = Modifier.testTag("auto-connect-switch").sizeIn(minWidth = 48.dp, minHeight = 48.dp))
        }
        if (!s.online) TextButton(onClick = onConnect, modifier = Modifier.testTag("more-retry-root")) { Text("Retry connection") }
        else TextButton(onClick = onDisconnect, modifier = Modifier.testTag("more-disconnect-root")) { Text("Disconnect root session") }
        InfoPanel("BKX background authority", when {
            bkxAuthorityRunning && bkxPeerConnected -> "Service active · local authority peer connected (not proof of BKX authorization)"
            bkxAuthorityRunning -> "Service active · waiting for verified authority peer"
            bkxStarting -> "Starting foreground service · not yet active"
            bkxStartFailed -> "Failed to start · check Android foreground-service restrictions"
            else -> "Off · foreground root connection is independent"
        }, Modifier.testTag("bkx-authority-status"))
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.weight(1f)) {
                Text("Keep BKX bridge active in background", fontWeight = FontWeight.SemiBold)
                Text("If off, Skybind stops the BKX foreground service when this app leaves the screen.",
                    style = MaterialTheme.typography.bodySmall)
            }
            Switch(checked = bkxKeepBackground, onCheckedChange = onBkxKeepBackgroundChanged,
                modifier = Modifier.testTag("bkx-background-lifetime").sizeIn(minWidth = 48.dp, minHeight = 48.dp))
        }
        InfoPanel("Notification visibility", NativePresentation.notificationStatus(LocalContext.current) +
            " · BKX may still have an Android foreground-service indicator", Modifier.testTag("bkx-notification-status"))
        if (bkxAuthorityRunning) OutlinedButton(onClick = onDisableBkx, modifier = Modifier.testTag("bkx-disable")) { Text("Stop BKX bridge") }
        else OutlinedButton(onClick = onEnableBkx, modifier = Modifier.testTag("bkx-enable")) { Text("Enable BKX bridge") }
        InfoPanel("Skybind backend", s.serverVersion ?: "Unavailable until authenticated")
        InfoPanel("Mounts", if (s.online) "${s.mounts.size} configured; see Mounts tab for authoritative status" else "Not connected")
        InfoPanel("Permissions", "Root manager approval controls the app connection. No general command, external broker, or storage-wide permission is granted.")
        InfoPanel("Runtime integrity", when {
            !s.online -> "Unavailable without an authenticated root session"
            s.runtime == null -> "Not reported"
            s.runtime.ready && s.runtime.provenanceValid -> "Verified on disk · ${s.runtime.provider}; FUSE availability not implied"
            else -> "Module runtime integrity could not be verified"
        }, Modifier.testTag("diagnostics-runtime"))
        InfoPanel("FUSE/mount health", if (s.online) {
            "${s.mounts.count { it.state == "RUNNING" }} observed running · ${s.mounts.count { it.state == "DEGRADED" || it.state == "MOUNT_STALE" }} needing attention" +
                " · overall FUSE device health not reported"
        } else "Unavailable while disconnected", Modifier.testTag("diagnostics-fuse"))
        InfoPanel("Network", NativePresentation.androidNetwork(LocalContext.current) +
            " · provider access requires separate daemon confirmation", Modifier.testTag("diagnostics-network"))
        InfoPanel("Module version", "Not reported by the current runtime API; the provider is shown above only after authentication")
        val context = LocalContext.current
        var showSigner by rememberSaveable { mutableStateOf(false) }
        InfoPanel("Native app", "Skybind ${NativePresentation.version()} · Android API ${Build.VERSION.SDK_INT}",
            Modifier.testTag("about-app-version"))
        TextButton(onClick = { showSigner = !showSigner },
            modifier = Modifier.testTag("about-show-signer").heightIn(min = 48.dp)) {
            Text(if (showSigner) "Hide APK signing fingerprint" else "View APK signing fingerprint")
        }
        if (showSigner) InfoPanel("Installed APK certificate · SHA-256",
            NativePresentation.signer(context), Modifier.testTag("about-signer-sha256"))
        InfoPanel("Security and privacy", "Root permission is controlled by your root manager; privileged write actions require explicit previews. No remote secrets are displayed. BKX authority is optional and separate.")
        InfoPanel("Snapshot freshness", if (s.online && s.sampledAtMillis != null)
            "Last daemon read: ${NativePresentation.time(s.sampledAtMillis.toString())}. Refresh to re-check."
            else "No current authenticated snapshot", Modifier.testTag("diagnostics-freshness"))
        TextButton(onClick = { setShowActivity(true) }, modifier = Modifier.testTag("more-view-activity")) { Text("Activity journal →") }
    }
}
