package io.github.mikeyphw.skybind.bridge

import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import java.security.MessageDigest

/**
 * Trusted Android-side PackageManager verifier for R1 consumer authorization.
 * Caller identity and approvedSignerSha256 must come from a separate trusted
 * control plane; never expose this as a caller-selected Binder/daemon endpoint.
 * No signed assertion is exported to the Go daemon by this class alone.
 */
object R1PackageManagerAuthority {
    data class ApprovedPackage(
        val name: String,
        val uid: Int,
        val signerSha256: String,
        val userId: Int
    )

    data class VerifiedPackage(
        val name: String,
        val uid: Int,
        val signerSha256: String
    )

    fun verify(context: Context, approved: ApprovedPackage): VerifiedPackage {
        require(Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) { "PM signing info unavailable" }
        require(approved.name.matches(Regex("[A-Za-z][A-Za-z0-9_.]{2,254}"))) {
            "invalid approved package name"
        }
        require(approved.uid >= 10000 && approved.userId >= 0) { "invalid user/uid pin" }
        require(approved.signerSha256.matches(Regex("[0-9a-f]{64}"))) {
            "invalid signer pin"
        }
        val pm = context.packageManager
        val packages = pm.getPackagesForUid(approved.uid)?.toList()
            ?: throw SecurityException("package UID unavailable")
        if (packages != listOf(approved.name)) throw SecurityException("UID package set mismatch")
        val info = pm.getApplicationInfo(approved.name, 0)
        if (info.uid != approved.uid) throw SecurityException("installed UID mismatch")
        if (android.os.UserHandle.getUserHandleForUid(info.uid).identifier != approved.userId)
            throw SecurityException("installed Android user mismatch")
        val signing = pm.getPackageInfo(
            approved.name, PackageManager.GET_SIGNING_CERTIFICATES
        ).signingInfo ?: throw SecurityException("signing info unavailable")
        val contents = signing.apkContentsSigners
        if (contents.size != 1) throw SecurityException("multi-signer requires separate policy")
        val digest = MessageDigest.getInstance("SHA-256")
            .digest(contents.single().toByteArray())
            .joinToString("") { "%02x".format(it) }
        if (!MessageDigest.isEqual(digest.toByteArray(Charsets.US_ASCII),
                approved.signerSha256.toByteArray(Charsets.US_ASCII))) {
            throw SecurityException("unapproved BKX signing identity")
        }
        return VerifiedPackage(approved.name, approved.uid, digest)
    }
}
