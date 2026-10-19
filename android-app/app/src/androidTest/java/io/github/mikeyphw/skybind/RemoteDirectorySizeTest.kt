package io.github.mikeyphw.skybind

import androidx.test.ext.junit.runners.AndroidJUnit4
import io.github.mikeyphw.skybind.bridge.RemoteBrowseReader
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.fail
import org.junit.Test
import org.junit.runner.RunWith

/** Test-only daemon replies: no root grant, network, secret or mutation. */
@RunWith(AndroidJUnit4::class)
class RemoteDirectorySizeTest {
    private fun read(vararg entries: JSONObject) = RemoteBrowseReader().fetch("fixture", "") { operation, args ->
        assertEquals("provider.browse", operation)
        assertEquals("fixture:", JSONObject(args).getString("remote"))
        JSONObject().put("schema_version", 1).put("ok", true)
            .put("result", JSONArray().also { array -> entries.forEach { array.put(it) } }).toString()
    }

    private fun entry(name: String, directory: Boolean, size: Long) = JSONObject()
        .put("Name", name).put("Path", name).put("IsDir", directory).put("Size", size)

    @Test fun permitsSevenUnknownSizeDirectoriesAndSixteenFiles() {
        val entries = (0 until 7).map { entry("dir$it", true, -1) } +
            (0 until 16).map { entry("file$it", false, 123) }
        val actual = read(*entries.toTypedArray())
        assertEquals(23, actual.size)
        assertEquals(7, actual.count { it.directory && it.sizeBytes == -1L })
        assertEquals(16, actual.count { !it.directory && it.sizeBytes == 123L })
    }

    @Test fun rejectsNegativeFileSizeAndDirectoryBelowUnknownMarker() {
        for ((dir, size) in listOf(false to -1L, false to -2L, true to -2L)) {
            try {
                read(entry("entry", dir, size))
                fail("invalid negative size accepted")
            } catch (_: IllegalArgumentException) {
                // Required: invalid sizes still fail closed.
            }
        }
    }

    @Test fun permitsNonnegativeFileAndDirectorySizes() {
        assertEquals(2, read(entry("file", false, 0), entry("dir", true, 0)).size)
    }
}
