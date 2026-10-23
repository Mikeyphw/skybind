package io.github.mikeyphw.skybind.bridge

import android.app.Application
import android.content.ComponentName
import android.content.Intent
import android.content.ServiceConnection
import android.os.IBinder
import android.os.RemoteException
import org.json.JSONObject
import java.util.UUID
import com.topjohnwu.superuser.ipc.RootService
import io.github.mikeyphw.skybind.model.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/** Foreground auto-bind via the system root manager; no unapproved su/loopback fallback. */
class RootReadSession(private val app: Application, private val disconnected: () -> Unit) : SkybindReadOnlyGateway {
    @Volatile private var remote: IRootReadBridge? = null
    private var connection: ServiceConnection? = null
    @Volatile private var reader = LiveReadSnapshotReader()
    @Volatile private var sessionId = UUID.randomUUID().toString()

    suspend fun connect() {
        if (remote != null) return
        val (boundConnection, binder) = withTimeout(20_000L) {
            suspendCancellableCoroutine<Pair<ServiceConnection, IBinder>> { continuation ->
                val conn = object : ServiceConnection {
                    override fun onServiceConnected(name: ComponentName, service: IBinder) {
                        if (continuation.isActive) continuation.resume(this to service)
                    }
                    override fun onServiceDisconnected(name: ComponentName) {
                        // A superseded binding may deliver a late Binder callback.
                        // It must never clear a newer authenticated session.
                        if (connection !== this) return
                        transportLost()
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
        // Binder loss may race the suspended connect continuation; never resurrect
        // a connection whose ownership has already been invalidated.
        if (connection !== boundConnection) throw RemoteException("root binding expired during connect")
        remote = IRootReadBridge.Stub.asInterface(binder) ?: throw RemoteException("root Binder unavailable")
    }

    override suspend fun snapshot(): SkybindReadSnapshot = withContext(Dispatchers.IO) {
        val api = remote ?: return@withContext SkybindReadSnapshot(LinkState.NOT_AUTHORIZED,
            "Root authorization pending; approve Skybind in your root manager when prompted.")
        // A read started before a disconnect must never publish a result into a
        // replacement session or leave its cursor in the current reader.
        val ownedReader = reader
        try {
            val value = ownedReader.fetch { method, args -> api.query(method, args) }
            if (remote !== api || reader !== ownedReader) {
                SkybindReadSnapshot(LinkState.DISCONNECTED, "Authenticated session expired; reconnect required.")
            } else value
        } catch (cancel: CancellationException) {
            throw cancel
        } catch (e: SecurityException) {
            withContext(Dispatchers.Main) { transportLost() }
            SkybindReadSnapshot(LinkState.NOT_AUTHORIZED, "Root service rejected the client or its scope.")
        } catch (e: SnapshotStageException) {
            withContext(Dispatchers.Main) { transportLost() }
            SkybindReadSnapshot(LinkState.DISCONNECTED, "Snapshot rejected at ${e.operation}. Reconnect after checking daemon compatibility.")
        } catch (e: Exception) {
            withContext(Dispatchers.Main) { transportLost() }
            SkybindReadSnapshot(LinkState.DISCONNECTED, "Skybind daemon unavailable. Retry the connection.")
        }
    }

    suspend fun browse(remoteName: String, path: String): List<RemoteFileEntry> = withContext(Dispatchers.IO) {
        val api = remote ?: throw SecurityException("unpaired root service")
        try {
            val entries = RemoteBrowseReader().fetch(remoteName, path) { method, args -> api.query(method, args) }
            if (remote !== api) throw SecurityException("read-only session expired during listing")
            entries
        } catch (cancel: CancellationException) {
            throw cancel
        } catch (dead: RemoteException) {
            withContext(Dispatchers.Main) { transportLost() }
            throw dead
        }
    }

    /** The only mutating interface; never accepts a raw command, path, proof, or arbitrary job. */
    suspend fun previewJob(name: String): PreparedJob = withContext(Dispatchers.IO) {
        val api = remote ?: throw SecurityException("not connected")
        val current = sessionId
        try {
            val obj = JSONObject(api.previewJob(current, name))
            if (remote !== api || sessionId != current) throw SecurityException("session replaced")
            val id = obj.getString("id")
            val resultName = obj.getString("name")
            val kind = obj.getString("kind")
            if (resultName != name || kind !in setOf("check", "copy"))
                throw SecurityException("unverified job preview")
            PreparedJob(id, resultName, kind, obj.getString("source"), obj.getString("destination"))
        } catch (cancel: CancellationException) { throw cancel }
    }

    suspend fun startPreparedJob(preview: PreparedJob): String = withContext(Dispatchers.IO) {
        val api = remote ?: throw SecurityException("not connected")
        val current = sessionId
        val result = JSONObject(api.startPreparedJob(current, preview.id))
        if (remote !== api || sessionId != current) throw SecurityException("session replaced after submission")
        if (result.getString("name") != preview.name || result.getString("state") != "RUNNING")
            throw SecurityException("unverified launch")
        result.getString("id").also { require(Regex("[0-9a-f]{32}").matches(it)) }
    }

    suspend fun cancelOwnedRun(id: String): Unit = withContext(Dispatchers.IO) {
        val api = remote ?: throw SecurityException("not connected")
        val current = sessionId
        val result = JSONObject(api.cancelOwnedRun(current, id))
        if (remote !== api || sessionId != current || result.getString("id") != id)
            throw SecurityException("unverified cancellation")
    }

    /** Mount actions are exact typed Binder calls; root-only proofs never reach Android UI. */
    suspend fun previewMount(action: String, name: String): PreparedMountAction = withContext(Dispatchers.IO) {
        val api = remote ?: throw SecurityException("not connected")
        val current = sessionId
        require(action in setOf("start", "stop", "restart", "reconcile"))
        val raw = when (action) {
            "start" -> api.previewStartMount(current, name)
            "stop" -> api.previewStopMount(current, name)
            "restart" -> api.previewRestartMount(current, name)
            "reconcile" -> api.previewReconcileMount(current)
            else -> throw SecurityException("unreviewed mount action")
        }
        val obj = JSONObject(raw)
        if (remote !== api || sessionId != current || obj.getString("action") != action ||
            obj.getString("name") != name) throw SecurityException("mount preview identity drift")
        PreparedMountAction(obj.getString("id"), action, name,
            obj.getString("observed"), obj.getBoolean("desired"),
            obj.getString("mountpoint"), obj.getString("remote"), obj.getInt("configured_count"))
    }

    suspend fun confirmMount(preview: PreparedMountAction): Unit = withContext(Dispatchers.IO) {
        val api = remote ?: throw SecurityException("not connected")
        val current = sessionId
        val obj = JSONObject(api.confirmMount(current, preview.id))
        if (remote !== api || sessionId != current || obj.getString("action") != preview.action ||
            obj.getString("name") != preview.name || !obj.getBoolean("accepted") ||
            !obj.getBoolean("refresh_required")) throw SecurityException("unverified mount reply")
    }

    suspend fun loadMountRegistry(): MountRegistryView = withContext(Dispatchers.IO) {
        val api = remote ?: throw SecurityException("not connected")
        val owned = sessionId
        val obj = MountRegistryView.decode(api.readMountConfiguration(owned))
        if (remote !== api || sessionId != owned) throw SecurityException("stale registry response")
        obj
    }
    suspend fun previewConfig(action: String, original: String, draft: MountDraft?): PreparedConfigChange =
        withContext(Dispatchers.IO) {
            val api = remote ?: throw SecurityException("not connected")
            val owned = sessionId
            val reply = when (action) {
                "create" -> api.previewCreateMount(owned, requireNotNull(draft).encode())
                "edit" -> api.previewEditMount(owned, original, requireNotNull(draft).encode())
                "delete" -> api.previewDeleteMount(owned, original)
                else -> throw SecurityException("invalid config action")
            }
            val obj = JSONObject(reply)
            if (obj.has("field_errors")) {
                val errors = obj.getJSONArray("field_errors")
                val fields = mutableMapOf<String, String>()
                val allowed = setOf("name", "remote", "mountpoint", "vfs_profile", "cache_mode",
                    "network_mode", "log_level", "cache_max_bytes", "min_cache_free_bytes",
                    "cache_max_age_seconds", "dir_cache_seconds", "poll_seconds",
                    "min_battery_percent", "boot_settle_seconds", "network_settle_seconds",
                    "cache_low_percent", "cache_high_percent")
                require(errors.length() in 1..17)
                for (i in 0 until errors.length()) {
                    val item = errors.getJSONObject(i)
                    val field = item.getString("field")
                    require(field in allowed && field !in fields)
                    fields[field] = configErrorMessage(item.getString("code"))
                }
                throw ConfigFieldValidation(fields)
            }
            val name = if (action == "create") requireNotNull(draft).name else original
            if (remote !== api || sessionId != owned || obj.getString("action") != action ||
                obj.getString("name") != name) throw SecurityException("config preview identity mismatch")
            val effects = obj.getJSONArray("effects")
            PreparedConfigChange(obj.getString("id"), action, name, obj.getLong("base_revision"),
                (0 until effects.length()).map { effects.getString(it) },
                obj.getString("mountpoint"), obj.getString("remote"))
        }
    suspend fun applyConfig(preview: PreparedConfigChange): Long = withContext(Dispatchers.IO) {
        val api = remote ?: throw SecurityException("not connected")
        val owned = sessionId
        val obj = JSONObject(api.applyMountConfiguration(owned, preview.id))
        if (remote !== api || sessionId != owned || obj.getString("action") != preview.action ||
            obj.getString("name") != preview.name || !obj.getBoolean("refresh_required") ||
            obj.getLong("revision") != preview.baseRevision + 1)
            throw SecurityException("config apply result identity mismatch")
        obj.getLong("revision")
    }

    /** Rollback is explicitly reviewed as an ENTIRE-registry action. */
    suspend fun previewRollback(): PreparedRegistryRollback = withContext(Dispatchers.IO) {
        val api = remote ?: throw SecurityException("not connected")
        val owned = sessionId
        val obj = JSONObject(api.previewRollbackMountConfiguration(owned))
        if (remote !== api || sessionId != owned || obj.getString("scope") != "ENTIRE_REGISTRY")
            throw SecurityException("rollback preview identity mismatch")
        val id = obj.getString("id")
        require(Regex("[0-9a-fA-F-]{36}").matches(id))
        val effects = obj.getJSONArray("effects")
        require(effects.length() in 1..64)
        PreparedRegistryRollback(id, obj.getLong("base_revision"),
            (0 until effects.length()).map { effects.getString(it) })
    }
    suspend fun applyRollback(preview: PreparedRegistryRollback): Long = withContext(Dispatchers.IO) {
        val api = remote ?: throw SecurityException("not connected")
        val owned = sessionId
        val obj = JSONObject(api.applyRollbackMountConfiguration(owned, preview.id))
        if (remote !== api || sessionId != owned || obj.getString("scope") != "ENTIRE_REGISTRY" ||
            !obj.getBoolean("refresh_required") || obj.getLong("revision") != preview.baseRevision + 1)
            throw SecurityException("unverified rollback result")
        obj.getLong("revision")
    }

    /** The same app-owned failure transition used by real Binder disconnect callbacks.
     * Testing this path never terminates the privileged process or revokes grants.
     */
    fun transportLost() {
        if (connection == null && remote == null) return
        close()
        disconnected()
    }

    fun close() {
        // Invalidate the identity before unbind can produce a late callback.
        val old = connection
        val oldRemote = remote
        val oldSession = sessionId
        // Clear app authority BEFORE performing any Binder traffic or unbind.
        sessionId = UUID.randomUUID().toString()
        connection = null
        remote = null
        // Do not block the UI on a read already in flight: rotate the reader
        // instead of waiting for its synchronized RPC batch to finish.
        reader = LiveReadSnapshotReader()
        // Drop operation authority in the service if still reachable; otherwise
        // the random old session ID is already lost by this app instance.
        oldRemote?.let { runCatching { it.forgetSession(oldSession) } }
        old?.let { runCatching { RootService.unbind(it) } }
    }
}
