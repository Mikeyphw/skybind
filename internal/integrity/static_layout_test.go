package integrity

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"strings"
	"testing"
)

// Q05P5 regression: the reviewed NewFuture v1.75.0 static fusermount3
// distribution intentionally has TWO ELF payloads, without libfuse*.so.
// The old min-three check prevented Android from authenticating both.
func TestReviewedStaticHelperTwoFileInventory(t *testing.T) {
	sum := func(s string) string { h := sha256.Sum256([]byte(s)); return hex.EncodeToString(h[:]) }
	engine := "system/bin/rclone"
	helper := "system/vendor/bin/fusermount3"
	files := map[string]File{
		engine: {SHA256: sum("rclone"), Size: 6},
		helper: {SHA256: sum("helper"), Size: 6},
	}
	encode := func(provider string, members map[string]File) []byte {
		t.Helper()
		data, err := json.Marshal(Manifest{Schema: 1, Product: "Skybind", Provider: provider, Arch: "arm64", Engine: engine, Helper: helper, Files: members})
		if err != nil {
			t.Fatal(err)
		}
		return data
	}
	for _, provider := range []string{"bclone", "newfuture"} {
		t.Run(provider, func(t *testing.T) {
			manifest, err := Decode(encode(provider, files))
			if err != nil {
				t.Fatalf("valid two-file static helper inventory rejected: %v", err)
			}
			if len(manifest.Files) != 2 {
				t.Fatalf("unexpected inventory: %d", len(manifest.Files))
			}
			missing := map[string]File{engine: files[engine]}
			if _, err = Decode(encode(provider, missing)); err == nil {
				t.Fatal("missing helper accepted")
			}
			missing = map[string]File{helper: files[helper]}
			if _, err = Decode(encode(provider, missing)); err == nil {
				t.Fatal("missing engine accepted")
			}
			changed := map[string]File{engine: files[engine], helper: {SHA256: strings.Repeat("0", 64), Size: 0}}
			if _, err = Decode(encode(provider, changed)); err == nil {
				t.Fatal("invalid file size accepted")
			}
			changed = map[string]File{engine: files[engine], helper: files[helper], "../escape": {SHA256: sum("bad"), Size: 3}}
			if _, err = Decode(encode(provider, changed)); err == nil {
				t.Fatal("traversal accepted")
			}
		})
	}
}

func TestAPINativeLauncherProvenance(t *testing.T) {
	native := "system/bin/skybind-rclone-engine"
	launcher := "system/bin/rclone"
	alias := "system/bin/skybind-rclone"
	helper := "system/vendor/bin/fusermount3"
	sum := func(s string) string { h := sha256.Sum256([]byte(s)); return hex.EncodeToString(h[:]) }
	files := map[string]File{native: {SHA256: sum("engine"), Size: 6},
		launcher: {SHA256: sum("launcher"), Size: 8}, alias: {SHA256: sum("launcher"), Size: 8}, helper: {SHA256: sum("helper"), Size: 6}}
	obj, err := json.Marshal(Manifest{Schema: 1, Product: "Skybind", Provider: "bclone", Arch: "arm64", Engine: native, Helper: helper, Files: files})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := Decode(obj); err != nil {
		t.Fatal(err)
	}
	delete(files, alias)
	obj, _ = json.Marshal(Manifest{Schema: 1, Product: "Skybind", Provider: "bclone", Arch: "arm64", Engine: native, Helper: helper, Files: files})
	if _, err := Decode(obj); err == nil {
		t.Fatal("missing public alias accepted")
	}
	files[alias] = File{SHA256: sum("launcher"), Size: 8}
	delete(files, native)
	obj, _ = json.Marshal(Manifest{Schema: 1, Product: "Skybind", Provider: "bclone", Arch: "arm64", Engine: native, Helper: helper, Files: files})
	if _, err := Decode(obj); err == nil {
		t.Fatal("missing native engine accepted")
	}
}
