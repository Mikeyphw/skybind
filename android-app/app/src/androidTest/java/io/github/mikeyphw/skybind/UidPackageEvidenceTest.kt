package io.github.mikeyphw.skybind

import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import io.github.mikeyphw.skybind.security.UidPackageEvidence
import org.junit.Assert.assertFalse
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class UidPackageEvidenceTest {
    @Test fun deniesUnknownOrUnpinnedCaller() {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        assertFalse(UidPackageEvidence.verify(context, 0, context.packageName, ByteArray(32)))
        assertFalse(UidPackageEvidence.verify(context, android.os.Process.myUid(), context.packageName, ByteArray(0)))
        assertFalse(UidPackageEvidence.verify(context, android.os.Process.myUid(), "not.a.real.package", ByteArray(32)))
    }
}
