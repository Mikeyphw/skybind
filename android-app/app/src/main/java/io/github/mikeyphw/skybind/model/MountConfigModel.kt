package io.github.mikeyphw.skybind.model

import org.json.JSONArray
import org.json.JSONObject

/** Only daemon-public registry fields are serialized. Never carries args files or credentials. */
data class MountDraft(
    val name: String = "", val remote: String = "", val mountpoint: String = "",
    val enabled: Boolean = false, val readOnly: Boolean = false, val allowOther: Boolean = false,
    val vfsProfile: String = "balanced", val cacheMode: String = "full",
    val cacheMaxBytes: String = "0", val cacheMaxAgeSeconds: String = "0",
    val dirCacheSeconds: String = "0", val pollSeconds: String = "0",
    val logLevel: String = "INFO", val networkMode: String = "any",
    val chargingOnly: Boolean = false, val minBatteryPercent: String = "0",
    val minCacheFreeBytes: String = "0", val bootSettleSeconds: String = "0",
    val networkSettleSeconds: String = "0", val cacheHighPercent: String = "90",
    val cacheLowPercent: String = "75",
) {
    /** Field keys match the daemon's bounded structured validation contract. */
    fun fieldErrors(): Map<String, String> {
        val issues = linkedMapOf<String, String>()
        if (!Regex("[A-Za-z][A-Za-z0-9_-]{0,62}").matches(name))
            issues["name"] = "Use a letter followed by letters, digits, underscores or dashes (63 max)."
        if (remote.length > 1024 || !Regex("[A-Za-z0-9_.-]+:.*").matches(remote) ||
            remote.any { it == '\\' || it == '\n' || it == '\r' || it == '\u0000' })
            issues["remote"] = "Select a configured remote and an optional safe subdirectory."
        if (mountpoint.length > 256 || !mountpoint.startsWith("/") ||
            !(mountpoint.startsWith("/storage/") || mountpoint.startsWith("/mnt/")) ||
            mountpoint.contains("..") || mountpoint.contains("//") ||
            mountpoint.any { it == '\\' || it == '\n' || it == '\r' || it == '\u0000' })
            issues["mountpoint"] = "Use a clean absolute path under /storage/ or /mnt/."
        for ((field, pair) in mapOf(
            "vfs_profile" to (vfsProfile to setOf("", "streaming", "balanced", "offline", "offline-ready", "documents", "minimal", "read-only", "custom")),
            "cache_mode" to (cacheMode to setOf("", "off", "minimal", "writes", "full")),
            "log_level" to (logLevel to setOf("", "DEBUG", "INFO", "NOTICE", "ERROR")),
            "network_mode" to (networkMode to setOf("", "any", "wifi", "unmetered", "offline-allowed")))) {
            if (pair.first !in pair.second) issues[field] = "Choose an allowed value."
        }
        val amounts = mapOf(
            "cache_max_bytes" to (cacheMaxBytes to (1L shl 44)),
            "min_cache_free_bytes" to (minCacheFreeBytes to (1L shl 44)),
            "cache_max_age_seconds" to (cacheMaxAgeSeconds to 31536000L),
            "dir_cache_seconds" to (dirCacheSeconds to 31536000L),
            "poll_seconds" to (pollSeconds to 86400L),
            "min_battery_percent" to (minBatteryPercent to 100L),
            "boot_settle_seconds" to (bootSettleSeconds to 3600L),
            "network_settle_seconds" to (networkSettleSeconds to 3600L),
            "cache_high_percent" to (cacheHighPercent to 100L),
            "cache_low_percent" to (cacheLowPercent to 100L))
        for ((field, pair) in amounts) {
            val number = pair.first.toLongOrNull()
            if (!Regex("[0-9]{1,16}").matches(pair.first) || number == null || number !in 0..pair.second)
                issues[field] = "Enter a non-negative number within the supported range."
        }
        val low = cacheLowPercent.toIntOrNull()
        val high = cacheHighPercent.toIntOrNull()
        if (low != null && high != null && low > high)
            issues["cache_low_percent"] = "Low watermark cannot exceed the high watermark."
        return issues
    }
    fun encode(): String {
        require(Regex("[A-Za-z][A-Za-z0-9_-]{0,62}").matches(name))
        require(remote.length <= 1024 && Regex("[A-Za-z0-9_.-]+:.*").matches(remote) &&
            !remote.any { it == '\\' || it == '\n' || it == '\r' || it == '\u0000' })
        require(mountpoint.length <= 256 && mountpoint.startsWith("/") &&
            (mountpoint.startsWith("/storage/") || mountpoint.startsWith("/mnt/")) &&
            !mountpoint.contains("..") && !mountpoint.contains("//") &&
            !mountpoint.any { it == '\\' || it == '\n' || it == '\r' || it == '\u0000' })
        fun long(value: String, max: Long): Long {
            require(Regex("[0-9]{1,16}").matches(value))
            return value.toLong().also { require(it in 0..max) }
        }
        fun int(value: String, max: Int): Int = long(value, max.toLong()).toInt()
        require(vfsProfile in setOf("", "streaming", "balanced", "offline", "offline-ready", "documents", "minimal", "read-only", "custom"))
        require(cacheMode in setOf("", "off", "minimal", "writes", "full"))
        require(logLevel in setOf("", "DEBUG", "INFO", "NOTICE", "ERROR"))
        require(networkMode in setOf("", "any", "wifi", "unmetered", "offline-allowed"))
        val high = int(cacheHighPercent, 100)
        val low = int(cacheLowPercent, 100)
        require(low <= high)
        return JSONObject().put("name", name).put("remote", remote).put("mountpoint", mountpoint)
            .put("enabled", enabled).put("read_only", readOnly).put("allow_other", allowOther)
            .put("vfs_profile", vfsProfile).put("cache_mode", cacheMode)
            .put("cache_max_bytes", long(cacheMaxBytes, 1L shl 44))
            .put("cache_max_age_seconds", long(cacheMaxAgeSeconds, 31536000))
            .put("dir_cache_seconds", long(dirCacheSeconds, 31536000))
            .put("poll_seconds", long(pollSeconds, 86400))
            .put("log_level", logLevel).put("network_mode", networkMode)
            .put("charging_only", chargingOnly).put("min_battery_percent", int(minBatteryPercent, 100))
            .put("min_cache_free_bytes", long(minCacheFreeBytes, 1L shl 44))
            .put("boot_settle_seconds", int(bootSettleSeconds, 3600))
            .put("network_settle_seconds", int(networkSettleSeconds, 3600))
            .put("cache_high_percent", high).put("cache_low_percent", low).toString()
    }

    companion object {
        fun decode(o: JSONObject) = MountDraft(
            name = o.getString("name"), remote = o.getString("remote"), mountpoint = o.getString("mountpoint"),
            enabled = o.getBoolean("enabled"), readOnly = o.getBoolean("read_only"),
            allowOther = o.getBoolean("allow_other"), vfsProfile = o.getString("vfs_profile"),
            cacheMode = o.getString("cache_mode"), cacheMaxBytes = o.getLong("cache_max_bytes").toString(),
            cacheMaxAgeSeconds = o.getLong("cache_max_age_seconds").toString(),
            dirCacheSeconds = o.getLong("dir_cache_seconds").toString(),
            pollSeconds = o.getLong("poll_seconds").toString(), logLevel = o.getString("log_level"),
            networkMode = o.getString("network_mode"), chargingOnly = o.getBoolean("charging_only"),
            minBatteryPercent = o.getInt("min_battery_percent").toString(),
            minCacheFreeBytes = o.getLong("min_cache_free_bytes").toString(),
            bootSettleSeconds = o.getInt("boot_settle_seconds").toString(),
            networkSettleSeconds = o.getInt("network_settle_seconds").toString(),
            cacheHighPercent = o.getInt("cache_high_percent").toString(),
            cacheLowPercent = o.getInt("cache_low_percent").toString())
    }
}

data class MountRegistryView(val revision: Long, val mounts: List<MountDraft>) {
    companion object {
        fun decode(raw: String): MountRegistryView {
            val obj = JSONObject(raw)
            require(obj.getInt("schema_version") == 2)
            val revision = obj.getLong("revision")
            require(revision >= 0)
            val array = obj.getJSONArray("mounts")
            require(array.length() <= 64)
            val mounts = (0 until array.length()).map { MountDraft.decode(array.getJSONObject(it)) }
            require(mounts.map { it.name }.toSet().size == mounts.size)
            return MountRegistryView(revision, mounts)
        }
    }
}

data class PreparedConfigChange(
    val id: String, val action: String, val name: String, val baseRevision: Long,
    val effects: List<String>, val mountpoint: String, val remote: String,
)

/** One-use rollback ticket: the previous registry never crosses Binder. */
data class PreparedRegistryRollback(val id: String, val baseRevision: Long,
    val effects: List<String>)

class ConfigFieldValidation(val fields: Map<String, String>) : IllegalArgumentException("Invalid configuration fields")

/** Only known daemon codes are rendered; never display arbitrary provider text. */
fun configErrorMessage(code: String): String = when (code) {
    "INVALID_OR_DUPLICATE" -> "Name is invalid or already configured."
    "INVALID_REMOTE" -> "Remote must use the configured remote:path syntax."
    "INVALID_PATH" -> "Destination is not a clean absolute path."
    "OUTSIDE_SUPPORTED_STORAGE" -> "Destination must be under /storage/ or /mnt/."
    "PATH_TOO_LONG" -> "Destination exceeds 256 characters."
    "OVERLAPPING_DESTINATION" -> "Destination overlaps an existing mount."
    "INVALID_CHOICE" -> "Choose a supported policy option."
    "OUT_OF_RANGE" -> "Value is outside the daemon's supported range."
    "EXCEEDS_HIGH_WATERMARK" -> "Low watermark exceeds the high watermark."
    else -> "Invalid field; refresh and review."
}
