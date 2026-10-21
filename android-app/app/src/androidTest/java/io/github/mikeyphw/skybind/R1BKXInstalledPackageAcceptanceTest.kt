package io.github.mikeyphw.skybind

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import io.github.mikeyphw.skybind.bridge.R1PackageManagerAuthority
import org.junit.Assert.assertEquals
import org.junit.Assert.fail
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Explicit opt-in real installed BKX package/signing probe. This is platform
 * PackageManager evidence only; NOT an Android-to-Go trust channel, an issued
 * broker grant, or BKX process-level/external-provider qualification.
 * The signer pin MUST be independently approved by the operator, not copied
 * from an app request or auto-read and silently accepted.
 */
@RunWith(AndroidJUnit4::class)
class R1BKXInstalledPackageAcceptanceTest {
    @Test fun liveApprovedBKXSigningAndWrongSignerRejection() {
        val args = InstrumentationRegistry.getArguments()
        assumeTrue("SKYBIND_R1_BKX_PM_NOT_REQUESTED",
            args.getString("skybind.r1.bkx.pm.live") == "true")
        val signer = args.getString("skybind.r1.bkx.approved.sha256")
            ?: throw AssertionError("SKYBIND_R1_BLOCKED_OPERATOR_SIGNER_PIN_MISSING")
        val uid = args.getString("skybind.r1.bkx.approved.uid")?.toIntOrNull()
            ?: throw AssertionError("SKYBIND_R1_BLOCKED_OPERATOR_UID_PIN_MISSING")
        if (uid < 10000 || !Regex("[0-9a-f]{64}").matches(signer))
            throw AssertionError("SKYBIND_R1_BLOCKED_INVALID_OPERATOR_PIN")
        val context = ApplicationProvider.getApplicationContext<Context>()
        val approved = R1PackageManagerAuthority.ApprovedPackage(
            "com.mikeyphw.bkx.android", uid, signer, uid / 100_000)
        val result = R1PackageManagerAuthority.verify(context, approved)
        assertEquals("SKYBIND_R1_FAILED_BKX_UID", uid, result.uid)
        assertEquals("SKYBIND_R1_FAILED_BKX_PACKAGE", approved.name, result.name)
        try {
            R1PackageManagerAuthority.verify(context,
                approved.copy(signerSha256 = "0".repeat(64)))
            fail("SKYBIND_R1_FAILED_WRONG_SIGNER_ACCEPTED")
        } catch (_: SecurityException) {
            // Independent negative; do not issue or persist any grant.
        }
    }
}
