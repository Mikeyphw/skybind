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

/** Retained across Activity recreation; clears stale results and never self-enables root. */
class SkybindSessionViewModel(app: Application) : AndroidViewModel(app) {
    var snapshot by mutableStateOf(SkybindReadSnapshot(LinkState.NOT_AUTHORIZED,
        "Tap Connect to request read-only Skybind access."))
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
    private var operationJob: Job? = null
    private var progressWatch: Job? = null
    private var browsing: Job? = null
    private var browseGeneration = 0L

    private fun clearOperations() {
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
            snapshot = SkybindReadSnapshot(LinkState.DISCONNECTED, "Broker connection lost")
        }
    }
    private val coordinator = ReadOnlyCoordinator(bridge)
    private var active: Job? = null
    private var generation = 0L

    /** Explicit app-local disconnect; no root-manager revocation or daemon mutation. */
    fun disconnect() {
        active?.cancel()
        generation++
        clearBrowser()
        clearOperations()
        bridge.close()
        snapshot = SkybindReadSnapshot(LinkState.NOT_AUTHORIZED,
            "Read-only session disconnected. Tap Connect to reconnect.")
    }

    fun refresh() {
        clearBrowser()
        active?.cancel()
        val token = ++generation
        active = viewModelScope.launch {
            val value = coordinator.refresh()
            if (token == generation) snapshot = value
        }
    }

    fun connect() {
        clearBrowser()
        active?.cancel()
        val token = ++generation
        snapshot = SkybindReadSnapshot(LinkState.CONNECTING, "Requesting read-only root service access")
        clearOperations()
        active = viewModelScope.launch {
            val result = try {
                bridge.connect()
                coordinator.refresh()
            } catch (cancel: kotlinx.coroutines.CancellationException) {
                throw cancel
            } catch (_: Exception) {
                SkybindReadSnapshot(LinkState.NOT_AUTHORIZED,
                    "Connection not approved or root service unavailable")
            }
            if (token == generation) snapshot = result
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
