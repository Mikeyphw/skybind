package org.skybind.probe;

import android.app.Activity;
import android.os.Bundle;
import android.os.Process;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import org.json.JSONObject;

/** A normal Activity, not a root-shell or run-as visibility simulation. */
public final class ProbeActivity extends Activity {
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        JSONObject result = new JSONObject();
        String nonce = getIntent().getStringExtra("nonce");
        String path = getIntent().getStringExtra("path");
        try {
            result.put("schema_version", 1);
            result.put("package", getPackageName());
            result.put("uid", Process.myUid());
            result.put("nonce", nonce);
            result.put("path", path);
            result.put("status", "APP_READ_WRITE_FAIL");
            if (nonce == null || !nonce.matches("[0-9a-f]{32}") || path == null || !path.startsWith("/") || path.contains("..")) {
                throw new IllegalArgumentException("invalid probe input");
            }
            File dest = new File(path,".skybind-app-probe-" + nonce);
            byte[] bytes = nonce.getBytes(StandardCharsets.US_ASCII);
            if (bytes.length != 32) throw new IllegalArgumentException("length");
            try {
                try (FileOutputStream w = new FileOutputStream(dest, false)) {w.write(bytes);w.getFD().sync();}
                byte[] back = new byte[32];
                int n;
                try (FileInputStream r = new FileInputStream(dest)) {n = r.read(back);}
                boolean matches = java.util.Arrays.equals(bytes, back) && n == 32;
                result.put("write_bytes",bytes.length);
                result.put("read_bytes",n);
                result.put("read_matches",matches);
                if (!matches) throw new IllegalStateException("readback mismatch");
                result.put("status","APP_READ_WRITE_PASS");
            } finally {
                if (!dest.delete()) result.put("cleanup_warning",true);
            }
        } catch (Exception e) {
            try {result.put("error_type",e.getClass().getSimpleName());}catch (Exception ignored){}
        }
        try (FileOutputStream out = openFileOutput("skybind-probe.json",MODE_PRIVATE)) {
            out.write(result.toString().getBytes(StandardCharsets.UTF_8));out.getFD().sync();
        } catch (Exception ignored) {}
        finish();
    }
}
