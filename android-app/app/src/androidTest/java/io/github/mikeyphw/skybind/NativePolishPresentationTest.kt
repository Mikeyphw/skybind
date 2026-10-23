package io.github.mikeyphw.skybind

import androidx.test.ext.junit.runners.AndroidJUnit4
import io.github.mikeyphw.skybind.ui.NativePresentation
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class NativePolishPresentationTest {
    @Test fun byteUnitsDoNotInventTotals() {
        assertEquals("Unknown size", NativePresentation.bytes(-1))
        assertEquals("0 B", NativePresentation.bytes(0))
        assertEquals("1.0 KiB", NativePresentation.bytes(1024))
    }
    @Test fun unsupportedTimestampCannotBecomeFalseDate() {
        assertEquals("Time unavailable", NativePresentation.time("-1"))
        assertEquals("Time unavailable", NativePresentation.time("T3"))
        assertEquals("Time unavailable", NativePresentation.time("0"))
    }
    @Test fun operationNamesAreReadableWithoutLeakingIds() {
        assertEquals("Job Progress", NativePresentation.label("job.progress"))
    }
}
