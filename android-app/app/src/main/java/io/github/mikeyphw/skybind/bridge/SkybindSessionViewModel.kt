package io.github.mikeyphw.skybind.bridge

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import io.github.mikeyphw.skybind.model.*
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/** Retained across rotation; foreground-only automatic root-manager approval. */
class SkybindSessionViewModel(app: Application) : AndroidViewModel(app) {
    var snapshot by mutableStateOf(SkybindReadSnapshot(LinkState.NOT_AUTHORIZED,
        "Connecting automatically when Skybind opens."))
        private set
    var browser by mutableStateOf(BrowserState())
        private set
    var preparedJob by mutableStateOf<PreparedJob?>(null)
        private set
    var jobActionBusy by mutableStateOf(false)
        private set
    var jobActionError by mutableStateOf<String?>(null)
        private set
    var ownedRunIds by mutableStateOf<Set<String>>(emptySet())
        private set
    var preparedMount by mutableStateOf<PreparedMountAction?>(null)
        private set
    var mountActionBusy by mutableStateOf(false)
        private set
    var mountActionError by mutableStateOf<String?>(null)
        private set
    var mountConfigDraft by mutableStateOf<MountDraft?>(null)
        private set
    var mountConfigMode by mutableStateOf<String?>(null)
        private set
    var mountConfigOriginal by mutableStateOf("")
        private set
    var configPreview by mutableStateOf<PreparedConfigChange?>(null)
        private set
    var configBusy by mutableStateOf(false)
        private set
    var configError by mutableStateOf<String?>(null)
        private set
    var configFieldErrors by mutableStateOf<Map<String, String>>(emptyMap())
        private set
    var rollbackPreview by mutableStateOf<PreparedRegistryRollback?>(null)
        private set
    var rollbackBusy by mutableStateOf(false)
        private set
    var rollbackError by mutableStateOf<String?>(null)
        private set
    private var rollbackOperation: Job? = null
    private var configOperation: Job? = null
    private var mountOperation: Job? = null
    private var operationJob: Job? = null
    private var progressWatch: Job? = null
    private var browsing: Job? = null
    private var browseGeneration = 0L
    var autoConnectEnabled by mutableStateOf(app.getSharedPreferences("skybind_native", 0)
        .getBoolean("auto_connect", true))
        private set
    private var foreground = false
    private var initialAttempted = false
    private var reconnectUsed = false
    private var resumeReconnectPending = false
    private var explicitlyDisconnected = false

    fun setAutoConnectEnabled(enabled: Boolean) {
        autoConnectEnabled = enabled
        getApplication<Application>().getSharedPreferences("skybind_native", 0).edit()
            .putBoolean("auto_connect", enabled).apply()
        if (enabled && foreground && !snapshot.online) connect()
    }

    /** Called only by Activity foreground lifecycle, once per ViewModel lifetime. */
    fun onForeground() {
        foreground = true
        if (autoConnectEnabled && !explicitlyDisconnected &&
            (!initialAttempted || (resumeReconnectPending && snapshot.link == LinkState.DISCONNECTED))) {
            initialAttempted = true
            resumeReconnectPending = false
            connectInternal()
        }
    }

    fun onBackground() { foreground = false }


    private fun clearOperations() {
        mountOperation?.cancel()
        configOperation?.cancel()
        rollbackOperation?.cancel()
        rollbackPreview = null
        rollbackBusy = false
        rollbackError = null
        mountConfigDraft = null
        mountConfigMode = null
        configPreview = null
        configBusy = false
        configError = null
        configFieldErrors = emptyMap()
        preparedMount = null
        mountActionBusy = false
        mountActionError = null
        operationJob?.cancel()
        progressWatch?.cancel()
        jobActionBusy = false
        preparedJob = null
        jobActionError = null
        ownedRunIds = emptySet()
    }

    private fun clearBrowser() {
        browsing?.cancel()
        browseGeneration++
        browser = BrowserState()
    }

    private val bridge = RootReadSession(app) {
        viewModelScope.launch {
            active?.cancel()
            clearBrowser()
            clearOperations()
            generation++
            // Rebind once on next foreground only if this was an authenticated
            // connection. A denied root prompt must never auto-loop on resume.
            resumeReconnectPending = !foreground && snapshot.online
            snapshot = SkybindReadSnapshot(LinkState.DISCONNECTED, "Broker connection lost")
            if (foreground && autoConnectEnabled && !explicitlyDisconnected && !reconnectUsed) {
                reconnectUsed = true
                val lostGeneration = generation
                viewModelScope.launch {
                    delay(1_500L)
                    if (foreground && generation == lostGeneration &&
                        snapshot.link == LinkState.DISCONNECTED) connectInternal()
                }
            }
        }
    }
    private val coordinator = ReadOnlyCoordinator(bridge)
    private var active: Job? = null
    private var generation = 0L

    /** Explicit app-local disconnect; no root-manager revocation or daemon mutation. */
    fun disconnect() {
        explicitlyDisconnected = true
        resumeReconnectPending = false
        active?.cancel()
        generation++
        clearBrowser()
        clearOperations()
        bridge.close()
        snapshot = SkybindReadSnapshot(LinkState.DISCONNECTED,
            "Disconnected by you. Select Retry to reconnect.")
    }

    fun refresh() {
        if (!snapshot.online) { connect(); return }
        active?.cancel()
        val token = ++generation
        val oldRemote = browser.remote
        val oldPath = browser.path
        active = viewModelScope.launch {
            val value = coordinator.refresh()
            if (token == generation) {
                snapshot = value
                if (!value.online || oldRemote != null && value.remotes.none { it.id == oldRemote })
                    clearBrowser()
                else if (oldRemote != null) browseAt(oldRemote, oldPath)
            }
        }
    }

    fun connect() {
        explicitlyDisconnected = false
        resumeReconnectPending = false
        initialAttempted = true
        reconnectUsed = true // manual Retry is never followed by automatic prompt loops
        connectInternal()
    }

    private fun connectInternal() {
        if (snapshot.link == LinkState.CONNECTING || snapshot.online) return
        clearBrowser()
        active?.cancel()
        val token = ++generation
        snapshot = SkybindReadSnapshot(LinkState.CONNECTING, "Connecting through your root manager")
        clearOperations()
        active = viewModelScope.launch {
            val result = try {
                bridge.connect()
                coordinator.refresh()
            } catch (cancel: kotlinx.coroutines.CancellationException) {
                throw cancel
            } catch (_: Exception) {
                SkybindReadSnapshot(LinkState.NOT_AUTHORIZED,
                    "Root approval was denied or the service is unavailable. Retry when ready.")
            }
            if (token == generation) snapshot = result
        }
    }

    /** A Mounts screen gesture opens the editor; no config RPC occurs during auto-root. */
    fun openMountEditor(action: String, name: String = "") {
        if (!snapshot.online || configBusy || rollbackBusy || mountConfigMode != null || preparedMount != null) return
        if (action !in setOf("create", "edit", "delete")) return
        if (action != "create" && snapshot.mounts.none { it.id == name }) return
        configError = null
        configBusy = true
        val token = generation
        configOperation = viewModelScope.launch {
            try {
                val registry = bridge.loadMountRegistry()
                if (token != generation || !snapshot.online) return@launch
                val existing = registry.mounts.firstOrNull { it.name == name }
                if (action != "create" && existing == null) throw SecurityException("mount not configured")
                mountConfigMode = action
                mountConfigOriginal = if (action == "create") "" else name
                mountConfigDraft = existing ?: MountDraft()
            } catch (cancel: kotlinx.coroutines.CancellationException) { throw cancel }
            catch (_: Exception) { if (token == generation) configError =
                "The current mount configuration is unavailable. Refresh before editing." }
            finally { if (token == generation) configBusy = false }
        }
    }

    fun updateMountDraft(next: MountDraft) {
        if (mountConfigMode !in setOf("create", "edit") || configBusy) return
        mountConfigDraft = next
        configPreview = null
        configError = null
        configFieldErrors = next.fieldErrors()
    }

    fun dismissMountEditor() {
        if (configBusy) return
        mountConfigMode = null
        mountConfigDraft = null
        mountConfigOriginal = ""
        configPreview = null
        configError = null
        configFieldErrors = emptyMap()
    }

    fun previewMountConfig() {
        val action = mountConfigMode ?: return
        val draft = mountConfigDraft ?: return
        if (!snapshot.online || configBusy || rollbackBusy || configPreview != null) return
        val localErrors = if (action == "delete") emptyMap() else draft.fieldErrors()
        if (localErrors.isNotEmpty()) {
            configFieldErrors = localErrors
            configError = "Correct the highlighted fields before preview."
            return
        }
        configFieldErrors = emptyMap()
        configError = null
        configBusy = true
        val token = generation
        configOperation = viewModelScope.launch {
            try {
                val preview = bridge.previewConfig(action, mountConfigOriginal,
                    if (action == "delete") null else draft)
                if (token == generation && mountConfigMode == action && snapshot.online)
                    configPreview = preview
            } catch (cancel: kotlinx.coroutines.CancellationException) { throw cancel }
            catch (validation: ConfigFieldValidation) {
                if (token == generation) {
                    configFieldErrors = validation.fields
                    configError = "Daemon validation identified specific fields; review them before retrying."
                }
            }
            catch (_: Exception) { if (token == generation) configError =
                "Daemon rejected the proposed configuration or its revision. Refresh before retrying." }
            finally { if (token == generation) configBusy = false }
        }
    }

    /** Preview is consumed locally before attempting a single daemon transaction. */
    fun applyMountConfig() {
        val preview = configPreview ?: return
        if (!snapshot.online || configBusy) return
        configPreview = null
        configBusy = true
        configError = null
        val token = generation
        configOperation = viewModelScope.launch {
            try {
                bridge.applyConfig(preview)
                if (token == generation && snapshot.online) {
                    val updated = coordinator.refresh()
                    if (token == generation) {
                        snapshot = updated
                        mountConfigMode = null
                        mountConfigDraft = null
                        mountConfigOriginal = ""
                    }
                }
            } catch (cancel: kotlinx.coroutines.CancellationException) { throw cancel }
            catch (_: Exception) { if (token == generation) configError =
                "Apply result uncertain or rejected. Refresh Mounts and review the registry before making another change." }
            finally { if (token == generation) configBusy = false }
        }
    }

    /** Roll back the entire registry to the daemon's previous-known-good version. */
    fun previewRegistryRollback() {
        if (!snapshot.online || rollbackBusy || configBusy || mountConfigMode != null ||
            preparedMount != null || rollbackPreview != null) return
        rollbackBusy = true
        rollbackError = null
        val token = generation
        rollbackOperation = viewModelScope.launch {
            try {
                val value = bridge.previewRollback()
                if (token == generation && snapshot.online) rollbackPreview = value
            } catch (cancel: kotlinx.coroutines.CancellationException) { throw cancel }
            catch (_: Exception) { if (token == generation) rollbackError =
                "Rollback unavailable. There may be no previous registry, or the daemon refused the preview." }
            finally { if (token == generation) rollbackBusy = false }
        }
    }

    fun dismissRegistryRollback() {
        if (!rollbackBusy) { rollbackPreview = null; rollbackError = null }
    }

    /** Consumes the one-use ticket before submitting one RPC; never retry automatically. */
    fun confirmRegistryRollback() {
        val ticket = rollbackPreview ?: return
        if (!snapshot.online || rollbackBusy || configBusy) return
        rollbackPreview = null
        rollbackBusy = true
        rollbackError = null
        val token = generation
        rollbackOperation = viewModelScope.launch {
            try {
                bridge.applyRollback(ticket)
                if (token == generation && snapshot.online) {
                    val value = coordinator.refresh()
                    if (token == generation) snapshot = value
                }
            } catch (cancel: kotlinx.coroutines.CancellationException) { throw cancel }
            catch (_: Exception) { if (token == generation) rollbackError =
                "Rollback result uncertain or rejected. Refresh the full registry before requesting a fresh preview." }
            finally { if (token == generation) rollbackBusy = false }
        }
    }

    /** A Mounts button, never foreground binding or refresh, starts this two-step flow. */
    fun previewMount(action: String, name: String) {
        if (!snapshot.online || mountActionBusy || preparedMount != null) return
        if (action !in setOf("start", "stop", "restart", "reconcile")) return
        if (action == "reconcile" && name.isNotEmpty()) return
        if (action != "reconcile" && snapshot.mounts.none { it.id == name }) return
        mountActionBusy = true
        mountActionError = null
        val token = generation
        mountOperation = viewModelScope.launch {
            try {
                val plan = bridge.previewMount(action, name)
                if (token == generation && snapshot.online) preparedMount = plan
            } catch (cancel: kotlinx.coroutines.CancellationException) { throw cancel }
            catch (_: Exception) { if (token == generation) mountActionError =
                "Mount preview unavailable. Refresh state before trying again." }
            finally { if (token == generation) mountActionBusy = false }
        }
    }

    fun dismissMountPreview() { preparedMount = null; mountActionError = null }

    /** One explicit confirm -> one consumed root ticket -> one daemon attempt. */
    fun confirmPreparedMount() {
        val plan = preparedMount ?: return
        if (!snapshot.online || mountActionBusy) return
        preparedMount = null
        mountActionBusy = true
        mountActionError = null
        val token = generation
        mountOperation = viewModelScope.launch {
            try {
                bridge.confirmMount(plan)
                if (token == generation && snapshot.online) {
                    // Confirmed submission still requires fresh daemon-authoritative state.
                    val value = coordinator.refresh()
                    if (token == generation) snapshot = value
                }
            } catch (cancel: kotlinx.coroutines.CancellationException) { throw cancel }
            catch (_: Exception) { if (token == generation) mountActionError =
                "Result uncertain or rejected. Refresh authoritative Mounts before a new preview; do not retry blindly." }
            finally { if (token == generation) mountActionBusy = false }
        }
    }

    /** Never submit from refresh or navigation. Preview must be an explicit Jobs gesture. */
    fun previewJob(name: String) {
        if (!snapshot.online || snapshot.definitions.none {
            it.name == name && it.kind in setOf("check", "copy") }) return
        if (jobActionBusy) return
        operationJob?.cancel()
        preparedJob = null
        jobActionError = null
        jobActionBusy = true
        val token = generation
        operationJob = viewModelScope.launch {
            try {
                val result = bridge.previewJob(name)
                if (token == generation && snapshot.online) preparedJob = result
            } catch (cancel: kotlinx.coroutines.CancellationException) { throw cancel }
            catch (_: Exception) { if (token == generation) jobActionError = "Job preview denied or unavailable" }
            finally { if (token == generation) jobActionBusy = false }
        }
    }

    fun dismissJobPreview() { preparedJob = null; jobActionError = null }

    /** A confirm button is the only path to daemon job.run; no implicit retry. */
    fun confirmPreparedJob() {
        val preview = preparedJob ?: return
        if (!snapshot.online || jobActionBusy) return
        jobActionBusy = true
        preparedJob = null // one-shot UI action even when daemon response is ambiguous
        jobActionError = null
        val token = generation
        operationJob = viewModelScope.launch {
            try {
                val id = bridge.startPreparedJob(preview)
                if (token == generation && snapshot.online) {
                    ownedRunIds = ownedRunIds + id
                    updateOperationsSnapshot(token)
                }
            } catch (cancel: kotlinx.coroutines.CancellationException) { throw cancel }
            catch (_: Exception) {
                if (token == generation) jobActionError =
                    "Launch result unverified. Refresh Jobs; do not submit again without a fresh preview."
            } finally { if (token == generation) jobActionBusy = false }
        }
    }

    fun cancelOwnedRun(id: String) {
        if (!snapshot.online || id !in ownedRunIds || jobActionBusy) return
        jobActionBusy = true
        jobActionError = null
        val token = generation
        operationJob = viewModelScope.launch {
            try {
                bridge.cancelOwnedRun(id)
                if (token == generation) {
                    ownedRunIds = ownedRunIds - id
                    updateOperationsSnapshot(token)
                }
            } catch (cancel: kotlinx.coroutines.CancellationException) { throw cancel }
            catch (_: Exception) {
                if (token == generation) jobActionError = "Cancel not verified; refresh authoritative job state."
            } finally { if (token == generation) jobActionBusy = false }
        }
    }

    /** Refreshes authoritative jobs/events without clearing an unrelated browser selection. */
    private suspend fun updateOperationsSnapshot(token: Long) {
        val value = coordinator.refresh()
        if (token == generation) {
            snapshot = value
            if (!value.online) clearOperations()
            else if (value.activeJobs.any { it.id in ownedRunIds }) startProgressWatch(token)
        }
    }

    private fun startProgressWatch(token: Long) {
        if (progressWatch?.isActive == true) return
        progressWatch = viewModelScope.launch {
            while (token == generation && snapshot.online &&
                snapshot.activeJobs.any { it.id in ownedRunIds }) {
                delay(3_000L)
                if (token != generation) break
                val value = coordinator.refresh()
                if (token == generation) snapshot = value
                if (!value.online) { clearOperations(); break }
            }
        }
    }

    /** Selection tokens discard completions from a previously chosen folder/session. */
    fun selectRemote(remoteName: String) {
        if (!snapshot.online || snapshot.remotes.none { it.id == remoteName }) {
            clearBrowser()
            return
        }
        browseAt(remoteName, "")
    }

    fun openFolder(name: String) {
        val remoteName = browser.remote ?: return
        if (!snapshot.online || browser.loading || browser.entries.none { it.name == name && it.directory }) return
        val next = runCatching { BrowseAddress.descend(browser.path, name) }.getOrNull() ?: return
        browseAt(remoteName, next)
    }

    fun parentFolder() {
        val remoteName = browser.remote ?: return
        if (!snapshot.online) { clearBrowser(); return }
        if (browser.path.isEmpty()) { clearBrowser(); return }
        browseAt(remoteName, BrowseAddress.parent(browser.path))
    }

    fun switchRemote() = clearBrowser()

    private fun browseAt(remoteName: String, path: String) {
        if (!snapshot.online || snapshot.remotes.none { it.id == remoteName }) { clearBrowser(); return }
        if (runCatching { BrowseAddress.endpoint(remoteName, path) }.isFailure) { clearBrowser(); return }
        browsing?.cancel()
        val token = ++browseGeneration
        browser = BrowserState(remote = remoteName, path = path, loading = true)
        browsing = viewModelScope.launch {
            val result = try {
                BrowserState(remote = remoteName, path = path, entries = bridge.browse(remoteName, path))
            } catch (cancel: kotlinx.coroutines.CancellationException) {
                throw cancel
            } catch (_: Exception) {
                BrowserState(remote = remoteName, path = path, error = "Listing unavailable or rejected by the daemon")
            }
            if (token == browseGeneration && snapshot.online &&
                snapshot.remotes.any { it.id == remoteName }) browser = result
        }
    }

    override fun onCleared() {
        clearBrowser()
        clearOperations()
        bridge.close()
        super.onCleared()
    }
}
