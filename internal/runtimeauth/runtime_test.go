package runtimeauth

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"skybind/internal/integrity"
	"testing"
)

func TestFixture(t *testing.T) {
	d := t.TempDir()
	files := map[string]integrity.File{}
	for _, n := range []string{"system/bin/rclone", "system/vendor/bin/fusermount3", "system/vendor/lib64/libfuse3.so"} {
		p := filepath.Join(d, n)
		if e := os.MkdirAll(filepath.Dir(p), 0700); e != nil {
			t.Fatal(e)
		}
		b := []byte(n)
		if e := os.WriteFile(p, b, 0700); e != nil {
			t.Fatal(e)
		}
		sum := sha256.Sum256(b)
		files[n] = integrity.File{SHA256: hex.EncodeToString(sum[:]), Size: int64(len(b))}
	}
	m := map[string]any{"schema_version": 1, "product": "Skybind", "provider": "newfuture", "arch": "arm64", "engine_path": "system/bin/rclone", "helper_path": "system/vendor/bin/fusermount3", "files": files}
	b, _ := json.Marshal(m)
	if e := os.WriteFile(filepath.Join(d, "runtime.provenance.json"), b, 0600); e != nil {
		t.Fatal(e)
	}
	if !inspect(d).Ready {
		t.Fatalf("valid: %+v", inspect(d))
	}
	os.WriteFile(filepath.Join(d, "system/bin/rclone"), []byte("bad"), 0700)
	if inspect(d).Ready {
		t.Fatal("tampering accepted")
	}
}
