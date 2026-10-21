package io.github.mikeyphw.skybind

import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import android.content.Context
import android.content.pm.PackageManager
import android.os.UserHandle
import io.github.mikeyphw.skybind.bridge.R1PackageManagerAuthority
import org.junit.Assert.assertEquals
import org.junit.Assert.fail
import org.junit.Test
import org.junit.runner.RunWith
import java.security.MessageDigest

/** Platform PM tests, source/CI-compiled but never a substitute for live R1 grant tests. */
@RunWith(AndroidJUnit4::class)
class R1PackageManagerAuthorityTest {
    private val context: Context get() = ApplicationProvider.getApplicationContext()

    @Test fun systemPackageInformationRequiresExactSignerAndUid() {
        val pm = context.packageManager
        val name = context.packageName
        val uid = pm.getApplicationInfo(name, 0).uid
        val signers = pm.getPackageInfo(name, PackageManager.GET_SIGNING_CERTIFICATES)
            .signingInfo!!.apkContentsSigners
        assertEquals(1, signers.size)
        val digest = MessageDigest.getInstance("SHA-256").digest(signers.single().toByteArray())
            .joinToString("") { "%02x".format(it) }
        val accepted = R1PackageManagerAuthority.ApprovedPackage(name, uid, digest, UserHandle.getUserHandleForUid(uid).identifier)
        assertEquals(uid, R1PackageManagerAuthority.verify(context, accepted).uid)
        val rejected = listOf(
            accepted.copy(signerSha256="0".repeat(64)),
            accepted.copy(uid=uid+1),
            accepted.copy(name="com.attacker.forged")
        )
        rejected.forEach { bad ->
            try { R1PackageManagerAuthority.verify(context,bad);fail("unapproved identity accepted") }
            catch (_: SecurityException) { }
            catch (_: IllegalArgumentException) { }
            catch (_: PackageManager.NameNotFoundException) { }
        }
    }
}
