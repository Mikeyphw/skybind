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
    private val bridge = RootReadSession(app) {
        viewModelScope.launch {
            active?.cancel()
            generation++
            snapshot = SkybindReadSnapshot(LinkState.DISCONNECTED, "Broker connection lost")
        }
    }
    private val coordinator = ReadOnlyCoordinator(bridge)
    private var active: Job? = null
    private var generation = 0L

    fun refresh() {
        active?.cancel()
        val token = ++generation
        active = viewModelScope.launch {
            val value = coordinator.refresh()
            if (token == generation) snapshot = value
        }
    }

    fun connect() {
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

    override fun onCleared() {
        bridge.close()
        super.onCleared()
    }
}
