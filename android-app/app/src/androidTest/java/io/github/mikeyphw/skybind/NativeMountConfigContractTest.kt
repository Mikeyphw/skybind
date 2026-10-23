package io.github.mikeyphw.skybind

import androidx.test.ext.junit.runners.AndroidJUnit4
import io.github.mikeyphw.skybind.model.MountDraft
import io.github.mikeyphw.skybind.model.MountRegistryView
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/** Pure schema and fail-closed identity cases; real root mutation is tested separately. */
@RunWith(AndroidJUnit4::class)
class NativeMountConfigContractTest {
    private fun safe() = MountDraft(name="photos", remote="cloud:Photos",
        mountpoint="/storage/emulated/0/CloudPhotos")

    @Test fun typedSchemaRoundtripRetainsAllPolicyFields() {
        val first = safe().copy(enabled=true, cacheMode="writes", cacheMaxBytes="1048576",
            minBatteryPercent="25", readOnly=true, pollSeconds="60",
            networkMode="wifi", cacheHighPercent="85", cacheLowPercent="65")
        val encoded=first.encode()
        assertEquals(first, MountDraft.decode(JSONObject(encoded)))
        assertFalse(encoded.contains("args_file"))
        assertFalse(encoded.contains("password"))
    }

    @Test fun rejectsUnsafePathsAndInvalidLimits() {
        for (draft in listOf(safe().copy(name="../../evil"),
            safe().copy(remote="unknown"), safe().copy(mountpoint="/data/adb/skybind"),
            safe().copy(mountpoint="/storage/../etc"),
            safe().copy(cacheMaxBytes="-1"),
            safe().copy(cacheHighPercent="65",cacheLowPercent="70"),
            safe().copy(networkMode="unreviewed"))) {
            assertTrue("invalid mount must fail: $draft", runCatching { draft.encode() }.isFailure)
        }
    }

    @Test fun rejectsInvalidSnapshotWithoutGuessingMounts() {
        val missing = """{"schema_version":2,"revision":4,"mounts":[{"name":"x"}]}"""
        assertTrue(runCatching { MountRegistryView.decode(missing) }.isFailure)
        assertTrue(runCatching { MountRegistryView.decode("""{"schema_version":3,"revision":4,"mounts":[]}""") }.isFailure)
    }
}
