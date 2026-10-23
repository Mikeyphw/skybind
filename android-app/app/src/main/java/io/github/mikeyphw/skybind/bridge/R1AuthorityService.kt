package io.github.mikeyphw.skybind.bridge

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import io.github.mikeyphw.skybind.MainActivity

/** Explicitly enabled, visible and non-sticky Android authority session.
 * Does not request root, issue grants or expose an exported binder.
 * The root gateway must independently authenticate this exact app identity.
 */
class R1AuthorityService : Service() {
    companion object {
        const val ACTION_START = "io.github.mikeyphw.skybind.r1.AUTHORITY_START"
        const val ACTION_STOP = "io.github.mikeyphw.skybind.r1.AUTHORITY_STOP"
        private const val CHANNEL = "skybind_r1_local_authority"
        private const val NOTIFICATION = 24011
        @Volatile var isRunning: Boolean = false
            private set
    }
    private val handler = Handler(Looper.getMainLooper())
    private val reconnect = object : Runnable {
        override fun run() {
            if (!isRunning) return
            // Idempotent while connected; retries only after genuine socket loss.
            R1PMBridgeAgent.start(applicationContext)
            handler.postDelayed(this, 3_000L)
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSelf()
            return START_NOT_STICKY
        }
        if (intent?.action != ACTION_START) {
            stopSelf()
            return START_NOT_STICKY
        }
        if (!isRunning) {
            try {
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(NotificationChannel(
                CHANNEL, "Skybind local authority", NotificationManager.IMPORTANCE_LOW
            ))
            val stop = PendingIntent.getService(
                this, 1, Intent(this, R1AuthorityService::class.java).setAction(ACTION_STOP),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
            )
            val open = PendingIntent.getActivity(
                this, 2, Intent(this, MainActivity::class.java),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
            )
            val note = Notification.Builder(this, CHANNEL)
                .setSmallIcon(io.github.mikeyphw.skybind.R.drawable.ic_stat_skybind)
                .setContentTitle("Skybind local authority active")
                .setContentText("User-enabled local identity bridge · no automatic grants")
                .setContentIntent(open)
                .setOngoing(true)
                .addAction(Notification.Action.Builder(android.R.drawable.ic_menu_close_clear_cancel, "Stop bridge", stop).build())
                .build()
            startForeground(NOTIFICATION, note)
            isRunning = true
            handler.post(reconnect)
            } catch (_: RuntimeException) {
                // Missing FGS authorization/notification restrictions: never report active.
                isRunning = false
                handler.removeCallbacks(reconnect)
                stopSelf()
                return START_NOT_STICKY
            }
        }
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        isRunning = false
        handler.removeCallbacks(reconnect)
        R1PMBridgeAgent.stop()
        super.onDestroy()
    }
}
