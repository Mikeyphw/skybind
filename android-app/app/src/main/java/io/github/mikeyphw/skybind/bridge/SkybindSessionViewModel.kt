package io.github.mikeyphw.skybind.bridge

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import io.github.mikeyphw.skybind.model.*
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

/** Retained across Activity recreation; clears stale results and never self-enables root. */
class SkybindSessionViewModel(app: Application) : AndroidViewModel(app) {
    var snapshot by mutableStateOf(SkybindReadSnapshot(LinkState.NOT_AUTHORIZED,
        "Tap Connect to request read-only Skybind access."))
        private set
    var browser by mutableStateOf(BrowserState())
        private set
    private var browsing: Job? = null
    private var browseGeneration = 0L

    private fun clearBrowser() {
        browsing?.cancel()
        browseGeneration++
        browser = BrowserState()
    }

    private val bridge = RootReadSession(app) {
        viewModelScope.launch {
            active?.cancel()
            clearBrowser()
            generation++
            snapshot = SkybindReadSnapshot(LinkState.DISCONNECTED, "Broker connection lost")
        }
    }
    private val coordinator = ReadOnlyCoordinator(bridge)
    private var active: Job? = null
    private var generation = 0L

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
        bridge.close()
        super.onCleared()
    }
}
