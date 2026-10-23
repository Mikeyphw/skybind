package io.github.mikeyphw.skybind.model

/** Confirmation has a root-service ticket, never a daemon proof or a root command. */
data class PreparedMountAction(
    val id: String, val action: String, val name: String,
    val observed: String, val desired: Boolean,
    val mountpoint: String = "", val remote: String = "",
    val configuredCount: Int = 0,
)
