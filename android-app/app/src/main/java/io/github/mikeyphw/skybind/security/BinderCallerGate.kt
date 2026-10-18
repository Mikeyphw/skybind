package io.github.mikeyphw.skybind.security

import android.content.Context
import android.os.Binder

/**
 * B1-C4 staging authority for *inbound Binder transaction handlers*.
 *
 * UID is read from Binder's transaction context, never from a Parcel, Intent,
 * socket payload or caller-provided JSON. Pins must be provisioned locally by
 * a trusted operator; passing a caller's claimed certificate as a pin is unsafe.
 *
 * This does not authenticate a Go Unix socket, mint grants, or enable a
 * cross-UID service. No exported Binder service is registered by this change.
 */
class BinderCallerGate(
    private val context: Context,
    approvedPins: Map<Int, UidPin> = emptyMap(),
) {
    data class UidPin(val packageName: String, val certificateSha256: ByteArray) {
        // ByteArray itself is mutable; copy before retaining the operator policy.
        fun copyPin() = UidPin(packageName, certificateSha256.clone())
    }

    private val pins: Map<Int, UidPin> = approvedPins.mapValues { it.value.copyPin() }

    /** Only call synchronously inside Binder.onTransact / an AIDL stub method. */
    fun approveOnTransact(): Boolean {
        val uid = Binder.getCallingUid()
        val pin = pins[uid] ?: return false
        return UidPackageEvidence.verify(context, uid, pin.packageName, pin.certificateSha256)
    }
}
