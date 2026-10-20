package io.github.mikeyphw.skybind.model

/** Display-only data. The daemon proof remains in the private privileged service. */
data class JobDefinition(val name: String, val kind: String, val enabled: Boolean)

data class PreparedJob(
    val id: String, val name: String, val kind: String,
    val source: String, val destination: String,
)
