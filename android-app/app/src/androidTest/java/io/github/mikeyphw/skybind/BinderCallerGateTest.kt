package io.github.mikeyphw.skybind

import android.content.Context
import android.content.pm.PackageManager
import android.os.Binder
import android.os.Parcel
import android.os.Process
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import io.github.mikeyphw.skybind.security.BinderCallerGate
import io.github.mikeyphw.skybind.security.UidPackageEvidence
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.security.MessageDigest

/** In-process Binder coverage only; a distinct-UID fixture is still required. */
@RunWith(AndroidJUnit4::class)
class BinderCallerGateTest {
    @Suppress("DEPRECATION")
    private fun installedPin(context: Context): ByteArray {
        val info = context.packageManager.getPackageInfo(
            context.packageName, PackageManager.GET_SIGNING_CERTIFICATES
        )
        val signers = requireNotNull(info.signingInfo).apkContentsSigners
        require(signers.size == 1)
        return MessageDigest.getInstance("SHA-256").digest(signers[0].toByteArray())
    }

    private fun transact(gate: BinderCallerGate): Int {
        val stub = object : Binder() {
            override fun onTransact(code: Int, data: Parcel, reply: Parcel?, flags: Int): Boolean {
                if (code != 100) return false
                reply?.writeInt(if (gate.approveOnTransact()) 1 else 0)
                return true
            }
        }
        val data = Parcel.obtain()
        val reply = Parcel.obtain()
        try {
            assertTrue(stub.transact(100, data, reply, 0))
            reply.setDataPosition(0)
            return reply.readInt()
        } finally {
            reply.recycle()
            data.recycle()
        }
    }

    @Test fun signedPackageOwnershipHasPositiveAndNegativeEvidence() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val pin = installedPin(context)
        assertTrue(UidPackageEvidence.verify(context, Process.myUid(), context.packageName, pin))
        val wrong = pin.clone().also { it[0] = (it[0].toInt() xor 0x01).toByte() }
        assertFalse(UidPackageEvidence.verify(context, Process.myUid(), context.packageName, wrong))
        assertFalse(UidPackageEvidence.verify(context, Process.myUid() + 1, context.packageName, pin))
    }

    @Test fun binderCallerGateDefaultsToDenyAndRequiresExactOperatorPin() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val uid = Process.myUid()
        val pin = installedPin(context)
        assertEquals(0, transact(BinderCallerGate(context)))
        val tampered = pin.clone().also { it[1] = (it[1].toInt() xor 0x01).toByte() }
        assertEquals(0, transact(BinderCallerGate(context,
            mapOf(uid to BinderCallerGate.UidPin(context.packageName, tampered)))))
        val policy = BinderCallerGate(context,
            mapOf(uid to BinderCallerGate.UidPin(context.packageName, pin)))
        pin.fill(0) // The gate must have copied the approved certificate pin.
        assertEquals(1, transact(policy))
    }
}
