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

func TestNewNativeRcloneLayoutIntegrity(t *testing.T) {
	root := t.TempDir()
	files := map[string]integrity.File{}
	members := []string{"system/bin/rclone", "system/bin/skybind-rclone", "system/bin/skybind-rclone-engine", "system/vendor/bin/fusermount3"}
	for _, name := range members {
		full := filepath.Join(root, name)
		if err := os.MkdirAll(filepath.Dir(full), 0700); err != nil {
			t.Fatal(err)
		}
		b := []byte("fixture:" + name)
		if err := os.WriteFile(full, b, 0700); err != nil {
			t.Fatal(err)
		}
		d := sha256.Sum256(b)
		files[name] = integrity.File{SHA256: hex.EncodeToString(d[:]), Size: int64(len(b))}
	}
	manifest := map[string]any{"schema_version": 1, "product": "Skybind", "provider": "bclone", "arch": "arm64",
		"engine_path": "system/bin/skybind-rclone-engine", "helper_path": "system/vendor/bin/fusermount3", "files": files}
	raw, err := json.Marshal(manifest)
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(filepath.Join(root, "runtime.provenance.json"), raw, 0600); err != nil {
		t.Fatal(err)
	}
	good := inspect(root)
	if !good.Ready || !good.ProvenanceValid || filepath.Base(good.Binary) != "skybind-rclone-engine" {
		t.Fatalf("native installed runtime rejected: %+v", good)
	}
	if err = os.WriteFile(filepath.Join(root, "system/bin/rclone"), []byte("altered"), 0700); err != nil {
		t.Fatal(err)
	}
	bad := inspect(root)
	if bad.Ready || bad.ProvenanceValid {
		t.Fatalf("tampered launcher accepted: %+v", bad)
	}
}
