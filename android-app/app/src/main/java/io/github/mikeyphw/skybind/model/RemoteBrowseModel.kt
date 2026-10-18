package io.github.mikeyphw.skybind.model

/** Only the active, fully authenticated folder listing may be rendered. */
data class RemoteFileEntry(val name: String, val directory: Boolean, val sizeBytes: Long)

data class BrowserState(
    val remote: String? = null,
    val path: String = "",
    val entries: List<RemoteFileEntry> = emptyList(),
    val loading: Boolean = false,
    val error: String? = null,
) {
    fun forSnapshot(snapshot: SkybindReadSnapshot): BrowserState =
        if (!snapshot.online || remote == null || snapshot.remotes.none { it.id == remote }) BrowserState()
        else this
}

/** Exact same segment safety as the daemon's non-mounting remote browser. */
object BrowseAddress {
    private val remotePattern = Regex("[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
    fun endpoint(remote: String, path: String): String {
        require(remotePattern.matches(remote)) { "invalid remote" }
        require(path.length <= 512 && !path.startsWith('/') && !path.contains('\\') &&
            !path.contains('\u0000') && !path.contains('\n') && !path.contains('\r')) { "invalid path" }
        if (path.isNotEmpty()) require(path.split('/').all {
            it.isNotEmpty() && it != "." && it != ".." && !it.contains(':')
        }) { "unsafe path segment" }
        return "$remote:$path"
    }
    fun descend(path: String, child: String): String {
        require(child.isNotEmpty() && child != "." && child != ".." &&
            !child.contains('/') && !child.contains('\\') && !child.contains(':') &&
            !child.contains('\u0000') && !child.contains('\n') && !child.contains('\r')) { "unsafe child" }
        val next = if (path.isEmpty()) child else "$path/$child"
        require(next.length <= 512) { "path too deep" }
        return next
    }
    fun parent(path: String): String = if ('/' in path) path.substringBeforeLast('/') else ""
}
