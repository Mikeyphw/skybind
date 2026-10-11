package runtimeauth

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"skybind/internal/integrity"
	"strings"
	"testing"
)

// The runtime authority must accept the exact two-member layout built by
// the Q04/Q05 candidate pipeline and still reject tampered/missing bytes.
func TestStaticTwoFileRuntimeStatus(t *testing.T) {
	for _, provider := range []string{"bclone", "newfuture"} {
		t.Run(provider, func(t *testing.T) {
			root := t.TempDir()
			files := make(map[string]integrity.File)
			for _, name := range []string{"system/bin/rclone", "system/vendor/bin/fusermount3"} {
				path := filepath.Join(root, name)
				if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
					t.Fatal(err)
				}
				payload := []byte("verified-" + name)
				if err := os.WriteFile(path, payload, 0755); err != nil {
					t.Fatal(err)
				}
				digest := sha256.Sum256(payload)
				files[name] = integrity.File{SHA256: hex.EncodeToString(digest[:]), Size: int64(len(payload))}
			}
			provenance := map[string]any{
				"schema_version": 1, "product": "Skybind", "provider": provider, "arch": "arm64",
				"engine_path": "system/bin/rclone", "helper_path": "system/vendor/bin/fusermount3", "files": files,
			}
			content, err := json.Marshal(provenance)
			if err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(filepath.Join(root, "runtime.provenance.json"), content, 0600); err != nil {
				t.Fatal(err)
			}
			status := inspect(root)
			if !status.Ready || !status.ProvenanceAvailable || !status.ProvenanceValid || status.Provider != provider {
				t.Fatalf("authentic static-helper module rejected: %+v", status)
			}
			helper := filepath.Join(root, "system/vendor/bin/fusermount3")
			if err := os.WriteFile(helper, []byte("tampered helper"), 0755); err != nil {
				t.Fatal(err)
			}
			status = inspect(root)
			if status.Ready || status.ProvenanceValid || !strings.Contains(status.Reason, "fusermount3") {
				t.Fatalf("tampered helper accepted or wrong failure: %+v", status)
			}
			if err := os.Remove(helper); err != nil {
				t.Fatal(err)
			}
			status = inspect(root)
			if status.Ready || status.ProvenanceValid {
				t.Fatalf("missing helper accepted: %+v", status)
			}
		})
	}
}
