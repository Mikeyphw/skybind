package io.github.mikeyphw.skybind.bridge

import android.app.Application
import android.content.ComponentName
import android.content.Intent
import android.content.ServiceConnection
import android.os.IBinder
import android.os.RemoteException
import com.topjohnwu.superuser.ipc.RootService
import io.github.mikeyphw.skybind.model.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/** Only an explicit UI gesture binds the root service. No automatic su/loopback fallback. */
class RootReadSession(private val app: Application, private val disconnected: () -> Unit) : SkybindReadOnlyGateway {
    @Volatile private var remote: IRootReadBridge? = null
    private var connection: ServiceConnection? = null
    private val reader = LiveReadSnapshotReader()

    suspend fun connect() {
        if (remote != null) return
        val binder = withTimeout(20_000L) {
            suspendCancellableCoroutine<IBinder> { continuation ->
                val conn = object : ServiceConnection {
                    override fun onServiceConnected(name: ComponentName, service: IBinder) {
                        if (continuation.isActive) continuation.resume(service)
                    }
                    override fun onServiceDisconnected(name: ComponentName) {
                        remote = null
                        reader.reset()
                        disconnected()
                    }
                    override fun onBindingDied(name: ComponentName) = onServiceDisconnected(name)
                    override fun onNullBinding(name: ComponentName) = onServiceDisconnected(name)
                }
                connection = conn
                continuation.invokeOnCancellation {
                    if (connection === conn) connection = null
                    runCatching { RootService.unbind(conn) }
                }
                try {
                    RootService.bind(Intent(app, RootReadBridgeService::class.java), conn)
                } catch (e: Exception) {
                    connection = null
                    if (continuation.isActive) continuation.resumeWithException(e)
                }
            }
        }
        remote = IRootReadBridge.Stub.asInterface(binder) ?: throw RemoteException("root Binder unavailable")
    }

    override suspend fun snapshot(): SkybindReadSnapshot = withContext(Dispatchers.IO) {
        val api = remote ?: return@withContext SkybindReadSnapshot(LinkState.NOT_AUTHORIZED,
            "Tap Connect and approve Skybind in your root manager to begin read-only access.")
        try {
            reader.fetch { method, args -> api.query(method, args) }
        } catch (e: SecurityException) {
            reader.reset()
            SkybindReadSnapshot(LinkState.NOT_AUTHORIZED, "Root service rejected the client or its scope.")
        } catch (e: Exception) {
            reader.reset()
            SkybindReadSnapshot(LinkState.DISCONNECTED, "Skybind daemon unavailable. Refresh to reconnect.")
        }
    }

    suspend fun browse(remoteName: String, path: String): List<RemoteFileEntry> = withContext(Dispatchers.IO) {
        val api = remote ?: throw SecurityException("unpaired root service")
        RemoteBrowseReader().fetch(remoteName, path) { method, args -> api.query(method, args) }
    }

    fun close() {
        reader.reset()
        remote = null
        connection?.let { runCatching { RootService.unbind(it) } }
        connection = null
    }
}
