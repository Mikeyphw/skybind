package io.github.mikeyphw.skybind.bridge

import io.github.mikeyphw.skybind.model.*
import org.json.JSONArray
import org.json.JSONObject

/** A separate read from the authoritative daemon, never filesystem access from app UID. */
class RemoteBrowseReader {
    fun fetch(remote: String, path: String, query: (String, String) -> String): List<RemoteFileEntry> {
        val endpoint = BrowseAddress.endpoint(remote, path)
        val response = JSONObject(query("provider.browse", JSONObject().put("remote", endpoint).toString()))
        require(response.optInt("schema_version", -1) == 1 && response.opt("ok") == true) {
            "remote listing refused by daemon"
        }
        val data = response.opt("result") as? JSONArray ?: error("unexpected listing format")
        require(data.length() <= 500) { "remote listing exceeds bound" }
        val entries = ArrayList<RemoteFileEntry>(data.length())
        val seen = HashSet<String>()
        for (i in 0 until data.length()) {
            val item = data.getJSONObject(i)
            val name = item.getString("Name")
            require(name.length in 1..255) { "invalid entry name" }
            val childPath = BrowseAddress.descend(path, name)
            BrowseAddress.endpoint(remote, childPath)
            require(seen.add(name)) { "duplicate entry" }
            val isDir = item.get("IsDir") as? Boolean ?: error("missing directory type")
            val size = item.getLong("Size")
            require(size >= 0 || (isDir && size == -1L)) { "invalid entry size" }
            // Reject provider-reported paths that disagree with the requested folder.
            val reported = item.getString("Path")
            require(reported == name || reported == childPath) { "entry outside requested folder" }
            entries += RemoteFileEntry(name, isDir, size)
        }
        return entries.sortedWith(compareByDescending<RemoteFileEntry> { it.directory }
            .thenBy(String.CASE_INSENSITIVE_ORDER) { it.name })
    }
}
