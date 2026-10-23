package io.github.mikeyphw.skybind.model

/** Source-of-truth boundaries: Jobs are snapshots; Activity is journal history. */
enum class LinkState { DISCONNECTED, CONNECTING, NOT_AUTHORIZED, ONLINE, DEGRADED, UNSUPPORTED }
enum class JobState { QUEUED, RUNNING, INTERRUPTED, COMPLETED, FAILED, CANCELLED }
enum class ActivitySeverity { INFO, WARNING, ERROR }

/** On-disk runtime integrity is not proof that the FUSE device or network works. */
data class RuntimeIntegrity(val ready: Boolean, val provenanceValid: Boolean, val provider: String)

data class RemoteSummary(val id: String, val displayName: String, val kind: String)
data class MountSummary(val id: String, val displayName: String, val state: String,
    val desired: Boolean = false, val reason: String = "",
    val recoveryAttempts: Int? = null, val recoveryClass: String? = null)
data class JobSummary(
    val id: String, val title: String, val state: JobState,
    val transferredBytes: Long = 0, val totalBytes: Long? = null,
    val speedBytesPerSecond: Double? = null, val etaSeconds: Long? = null,
    val percent: Double? = null, val filesDone: Long? = null, val filesTotal: Long? = null,
) {
    val actionable: Boolean get() = state == JobState.RUNNING || state == JobState.QUEUED || state == JobState.INTERRUPTED
}
data class ActivityRecord(
    val sequence: Long, val operationId: String?, val title: String,
    val occurredAt: String, val severity: ActivitySeverity,
)

data class SkybindReadSnapshot(
    val link: LinkState,
    val detail: String,
    val serverVersion: String? = null,
    val remotes: List<RemoteSummary> = emptyList(),
    val mounts: List<MountSummary> = emptyList(),
    val jobs: List<JobSummary> = emptyList(),
    val events: List<ActivityRecord> = emptyList(),
    val cursor: Long? = null,
    val hasEventGap: Boolean = false,
    val definitions: List<JobDefinition> = emptyList(),
    val runtime: RuntimeIntegrity? = null,
    val sampledAtMillis: Long? = null,
) {
    val online: Boolean get() = link == LinkState.ONLINE
    val activeJobs: List<JobSummary> get() = if (online) jobs.filter { it.actionable } else emptyList()
    val recentJobs: List<JobSummary> get() = if (online) jobs.filterNot { it.actionable } else emptyList()
    val timeline: List<ActivityRecord> get() = if (online) events.distinctBy { it.sequence }.sortedByDescending { it.sequence } else emptyList()

    /** Hide all untrusted/stale data on a disconnected, unproven session. */
    fun failClosed(): SkybindReadSnapshot = if (online) this else copy(
        serverVersion = null, remotes = emptyList(), mounts = emptyList(),
        jobs = emptyList(), events = emptyList(), cursor = null, hasEventGap = false,
        definitions = emptyList(), runtime = null, sampledAtMillis = null,
    )
}

/** A broker has to be authenticated *before* it can return ONLINE. */
interface SkybindReadOnlyGateway {
    suspend fun snapshot(): SkybindReadSnapshot
}

/** No root shell, guessed daemon socket, loopback server, or fabricated status. */
class UnpairedGateway : SkybindReadOnlyGateway {
    override suspend fun snapshot() = SkybindReadSnapshot(
        link = LinkState.NOT_AUTHORIZED,
        detail = "The trusted Skybind app-to-daemon connection is not configured yet.",
    )
}

class ReadOnlyCoordinator(private val gateway: SkybindReadOnlyGateway) {
    suspend fun refresh(): SkybindReadSnapshot = try {
        gateway.snapshot().failClosed()
    } catch (cancel: kotlin.coroutines.cancellation.CancellationException) {
        throw cancel
    } catch (_: Exception) {
        SkybindReadSnapshot(LinkState.DISCONNECTED, "Connection could not be established. No operation was submitted.")
    }
}
