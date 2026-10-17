package io.github.mikeyphw.skybind.security

import android.content.Context
import android.content.pm.PackageManager
import android.os.Build

/**
 * Android PackageManager-side local evidence helper. This does NOT establish an
 * authenticated channel to the privileged Go broker. No serialized evidence
 * from an untrusted app may be treated as a kernel or Binder identity proof.
 */
object UidPackageEvidence {
    /** Returns true only if one package owns this UID and Android's package
     * manager recognizes the exact 32-byte SHA-256 signing-certificate pin. */
    @Suppress("DEPRECATION")
    fun verify(context: Context, uid: Int, packageName: String, sha256: ByteArray): Boolean {
        if (uid < 10000 || sha256.size != 32 || packageName.isBlank()) return false
        val pm = context.packageManager
        val packages = pm.getPackagesForUid(uid) ?: return false
        if (packages.size != 1 || packages[0] != packageName) return false
        return try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                pm.hasSigningCertificate(packageName, sha256, PackageManager.CERT_INPUT_SHA256)
            } else {
                val info = pm.getPackageInfo(packageName, PackageManager.GET_SIGNATURES)
                val digest = java.security.MessageDigest.getInstance("SHA-256")
                val signatures = info.signatures ?: return false
                signatures.size == 1 &&
                    java.security.MessageDigest.isEqual(digest.digest(signatures[0].toByteArray()), sha256)
            }
        } catch (_: PackageManager.NameNotFoundException) {
            false
        } catch (_: SecurityException) {
            false
        }
    }
}
