package io.github.mikeyphw.skybind

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import io.github.mikeyphw.skybind.bridge.R1PMBridgeAgent
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test
import org.junit.runner.RunWith

/** Negative tests never open the authority socket or provision grants. */
@RunWith(AndroidJUnit4::class)
class R1PMBridgeAgentTest {
    private val context: Context get() = ApplicationProvider.getApplicationContext()
    private val nonce = "a".repeat(64)
    private fun request(pkg: String, uid: Int): String =
        JSONObject().put("version", 1).put("nonce", nonce)
            .put("uid", uid).put("package", pkg).toString()

    @Test fun deniesUnknownConsumer() {
        val out = JSONObject(R1PMBridgeAgent.answer(context, request("com.attacker.client", 10327)))
        assertEquals("not_authorized", out.getString("error"))
        assertFalse(out.has("record"))
    }
    @Test fun deniesUninstalledOrWrongUid() {
        val out = JSONObject(R1PMBridgeAgent.answer(context, request("com.mikeyphw.bkx.android", 19999)))
        assertEquals("not_authorized", out.getString("error"))
    }
    @Test fun deniesInvalidNonce() {
        val req = JSONObject(request("com.mikeyphw.bkx.android", 10327)).put("nonce", "forged")
        val out = JSONObject(R1PMBridgeAgent.answer(context, req.toString()))
        assertEquals("not_authorized", out.getString("error"))
    }
    @Test fun deniesUnknownFields() {
        val req = JSONObject(request("com.mikeyphw.bkx.android", 10327)).put("arbitrary_control", true)
        val out = JSONObject(R1PMBridgeAgent.answer(context, req.toString()))
        assertEquals("not_authorized", out.getString("error"))
    }
}
