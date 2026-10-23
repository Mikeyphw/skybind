package io.github.mikeyphw.skybind.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import io.github.mikeyphw.skybind.model.MountDraft
import io.github.mikeyphw.skybind.model.PreparedConfigChange

/** Four-step native configuration editor; no daemon operation until explicit Review. */
@Composable
fun MountConfigEditor(mode: String, original: String, draft: MountDraft,
    remoteNames: List<String>,
    preview: PreparedConfigChange?, busy: Boolean, error: String?,
    fieldErrors: Map<String, String>,
    onChange: (MountDraft) -> Unit, onPreview: () -> Unit, onApply: () -> Unit,
    onClose: () -> Unit) {
    var step by remember(mode, original) { mutableIntStateOf(if (mode == "delete") 3 else 0) }
    var advanced by remember(mode, original) { mutableStateOf(false) }
    var consent by remember(preview?.id) { mutableStateOf(false) }
    val localErrors = remember(draft) { if (mode == "delete") emptyMap() else draft.fieldErrors() }
    val encodedValid = remember(draft) { runCatching { draft.encode() }.isSuccess }
    val valid = localErrors.isEmpty() && encodedValid
    val currentErrors = localErrors + fieldErrors
    Dialog(onDismissRequest = { if (!busy) onClose() }) {
        Surface(shape = MaterialTheme.shapes.large, tonalElevation = 6.dp,
            modifier = Modifier.fillMaxWidth().testTag("config-editor-dialog")) {
            Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(when (mode) {
                    "create" -> "Create a mount"
                    "edit" -> "Edit $original"
                    else -> "Delete $original"
                }, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
                Text(if (mode == "delete") "Confirm removal of the configured mount"
                    else listOf("1 · Source", "2 · Destination", "3 · Behavior", "4 · Review")[step],
                    style = MaterialTheme.typography.labelMedium)
                Column(Modifier.heightIn(max = 480.dp).verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    if (mode == "delete") {
                        Text("The registry entry $original will be removed. The daemon must safely quiesce any owned running mount; cache cleanup is a separate operation.")
                    } else when (step) {
                        0 -> {
                            Text("Choose a configured rclone remote, including an optional subdirectory. No credentials are stored in the app.")
                            if (remoteNames.isNotEmpty()) {
                                Choice("Configured remotes", draft.remote.substringBefore(':'), remoteNames.take(24),
                                    { onChange(draft.copy(remote = "$it:")) })
                            }
                            Field("Remote endpoint (for example, cloud:Photos)", draft.remote,
                                { onChange(draft.copy(remote = it)) }, "config-source-remote")
                        }
                        1 -> {
                            Field("Mount name", draft.name, { onChange(draft.copy(name = it)) },
                                "config-destination-name", readOnly = mode == "edit")
                            Field("Absolute mountpoint (/storage/… or /mnt/…)", draft.mountpoint,
                                { onChange(draft.copy(mountpoint = it)) }, "config-destination-path")
                            Text("Overlapping mountpoints, unsafe paths and renamed mounts are rejected by the daemon.",
                                style = MaterialTheme.typography.bodySmall)
                        }
                        2 -> {
                            Toggle("Enabled in desired configuration", draft.enabled,
                                { onChange(draft.copy(enabled = it)) }, "config-enabled")
                            Toggle("Read-only filesystem", draft.readOnly,
                                { onChange(draft.copy(readOnly = it)) }, "config-readonly")
                            Toggle("Allow other users", draft.allowOther,
                                { onChange(draft.copy(allowOther = it)) }, "config-allow-other")
                            Choice("VFS profile", draft.vfsProfile,
                                listOf("balanced", "streaming", "offline-ready", "documents", "minimal", "read-only", "custom", "offline", ""),
                                { onChange(draft.copy(vfsProfile = it)) })
                            Choice("Cache mode", draft.cacheMode, listOf("full", "writes", "minimal", "off", ""),
                                { onChange(draft.copy(cacheMode = it)) })
                            Choice("Network mode", draft.networkMode,
                                listOf("any", "wifi", "unmetered", "offline-allowed", ""),
                                { onChange(draft.copy(networkMode = it)) })
                            Toggle("Charging required", draft.chargingOnly,
                                { onChange(draft.copy(chargingOnly = it)) }, "config-charging")
                            TextButton(onClick = { advanced = !advanced },
                                modifier = Modifier.testTag("config-advanced-toggle")) {
                                Text(if (advanced) "Hide advanced fields" else "Advanced policy and cache limits")
                            }
                            if (advanced) {
                                Choice("Log level", draft.logLevel, listOf("INFO", "NOTICE", "ERROR", "DEBUG", ""),
                                    { onChange(draft.copy(logLevel = it)) })
                                Field("Cache maximum bytes", draft.cacheMaxBytes, { onChange(draft.copy(cacheMaxBytes = it)) }, "config-cache-bytes")
                                Field("Cache max age seconds", draft.cacheMaxAgeSeconds, { onChange(draft.copy(cacheMaxAgeSeconds = it)) }, "config-cache-age")
                                Field("Directory cache seconds", draft.dirCacheSeconds, { onChange(draft.copy(dirCacheSeconds = it)) }, "config-dir-cache")
                                Field("Poll interval seconds", draft.pollSeconds, { onChange(draft.copy(pollSeconds = it)) }, "config-poll")
                                Field("Minimum battery percent", draft.minBatteryPercent, { onChange(draft.copy(minBatteryPercent = it)) }, "config-battery")
                                Field("Minimum free cache bytes", draft.minCacheFreeBytes, { onChange(draft.copy(minCacheFreeBytes = it)) }, "config-free-cache")
                                Field("Boot settle seconds", draft.bootSettleSeconds, { onChange(draft.copy(bootSettleSeconds = it)) }, "config-boot-settle")
                                Field("Network settle seconds", draft.networkSettleSeconds, { onChange(draft.copy(networkSettleSeconds = it)) }, "config-network-settle")
                                Field("Cache high watermark %", draft.cacheHighPercent, { onChange(draft.copy(cacheHighPercent = it)) }, "config-high-water")
                                Field("Cache low watermark %", draft.cacheLowPercent, { onChange(draft.copy(cacheLowPercent = it)) }, "config-low-water")
                            }
                        }
                        3 -> {
                            if (mode != "delete") {
                                Text("Name: ${draft.name}")
                                Text("Remote: ${draft.remote}")
                                Text("Destination: ${draft.mountpoint}")
                                Text("Enabled: ${draft.enabled} · Read-only: ${draft.readOnly}")
                                Text("Cache: ${draft.cacheMode} · VFS: ${draft.vfsProfile}")
                            }
                            if (preview == null) {
                                Text("Request daemon validation and a fresh one-use revision-bound proof before applying.")
                                Button(onClick = onPreview, enabled = !busy && (mode == "delete" || valid),
                                    modifier = Modifier.testTag("config-preview")) { Text("Validate & preview") }
                            } else {
                                Text("Base revision: ${preview.baseRevision}")
                                preview.effects.forEach { Text("Effect: $it") }
                                Text("Preview expires after 60 seconds. A conflict, unknown outcome, or daemon refusal needs a fresh review.",
                                    style = MaterialTheme.typography.bodySmall)
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Checkbox(checked = consent, onCheckedChange = { consent = it },
                                        modifier = Modifier.testTag("config-consent"))
                                    Text(if (mode == "delete") "I approve deleting this mount" else "I approve these configuration changes")
                                }
                            }
                        }
                    }
                    if (currentErrors.isNotEmpty()) {
                        val onStep = when (step) {
                            0 -> setOf("remote")
                            1 -> setOf("name", "mountpoint")
                            else -> currentErrors.keys
                        }
                        currentErrors.filterKeys { it in onStep }.forEach { (field, message) ->
                            Text("${field.replace('_', ' ')}: $message", color = MaterialTheme.colorScheme.error,
                                style = MaterialTheme.typography.bodySmall,
                                modifier = Modifier.testTag("config-field-error-$field"))
                        }
                    }
                    if (error != null) Text(error, color = MaterialTheme.colorScheme.error,
                        modifier = Modifier.testTag("config-error"))
                    if (!valid && mode != "delete") Text("Check required fields and numeric limits before preview.",
                        style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
                    if (busy) LinearProgressIndicator(Modifier.fillMaxWidth())
                }
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    TextButton(onClick = { if (step > 0 && mode != "delete") step-- else onClose() },
                        enabled = !busy, modifier = Modifier.testTag("config-back")) {
                        Text(if (step == 0 || mode == "delete") "Close" else "Back")
                    }
                    when {
                        step < 3 && mode != "delete" -> Button(onClick = { step++ }, enabled = !busy &&
                            currentErrors.none { (key, _) -> key in when (step) {
                                0 -> setOf("remote")
                                1 -> setOf("name", "mountpoint")
                                else -> currentErrors.keys
                            } },
                            modifier = Modifier.testTag("config-next")) { Text("Next") }
                        preview != null -> Button(onClick = onApply, enabled = !busy && consent,
                            modifier = Modifier.testTag("config-apply")) {
                            Text(if (mode == "delete") "Delete" else "Apply")
                        }
                        else -> Text("Review before saving", style = MaterialTheme.typography.labelSmall)
                    }
                }
            }
        }
    }
}

@Composable private fun Field(label: String, value: String, change: (String) -> Unit,
    tag: String, readOnly: Boolean = false) {
    OutlinedTextField(value = value, onValueChange = change, label = { Text(label) },
        singleLine = true, readOnly = readOnly,
        modifier = Modifier.fillMaxWidth().testTag(tag))
}

@Composable private fun Toggle(label: String, value: Boolean, change: (Boolean) -> Unit, tag: String) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(label, modifier = Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
        Switch(checked = value, onCheckedChange = change, modifier = Modifier.testTag(tag))
    }
}

@Composable private fun Choice(label: String, selected: String, values: List<String>, change: (String) -> Unit) {
    Text(label, style = MaterialTheme.typography.labelMedium)
    Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
        values.chunked(2).forEach { options ->
            Row(horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                options.forEach { value ->
                    FilterChip(selected = selected == value, onClick = { change(value) },
                        label = { Text(value.ifEmpty { "Default" }) })
                }
            }
        }
    }
}
