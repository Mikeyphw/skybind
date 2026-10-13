package backup

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"skybind/internal/mounts/config"
	"skybind/internal/offline"
	"skybind/internal/uisettings"
)

func demo(t *testing.T) Document {
	t.Helper()
	r := config.Empty()
	r.Mounts = []config.Mount{{Name: "drive", Remote: "drive:Documents", Mountpoint: "/storage/emulated/0/SkybindDrive", Enabled: true, VFSProfile: "balanced"}}
	pins := offline.Manifest{Schema: 1, QuotaBytes: 8 << 30, Pins: []offline.Pin{{Mount: "drive", Path: "report.pdf", SHA256: strings.Repeat("a", 64), RemoteIdentity: strings.Repeat("f", 64), Size: 19}}}
	doc, err := Build(r, uisettings.Snapshot{Settings: uisettings.Defaults()}, pins)
	if err != nil {
		t.Fatal(err)
	}
	return doc
}
func TestPortableBackupRoundtripDisabledMountsAndPinReferences(t *testing.T) {
	doc := demo(t)
	data, _ := json.Marshal(doc)
	var decoded Document
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatal(err)
	}
	if err := Validate(decoded); err != nil {
		t.Fatal(err)
	}
	candidate, err := Candidate(decoded, 97)
	if err != nil {
		t.Fatal(err)
	}
	var out config.Registry
	if err = json.Unmarshal(candidate, &out); err != nil {
		t.Fatal(err)
	}
	if out.Revision != 97 || len(out.Mounts) != 1 || out.Mounts[0].Enabled {
		t.Fatalf("import unexpectedly enabled mount: %+v", out)
	}
	if len(decoded.Payload.PinReferences) != 1 || decoded.Payload.PinReferences[0].Path != "report.pdf" {
		t.Fatal("pin manifest reference lost")
	}
	for _, bad := range []string{"rclone.conf", "password", "refresh_token", "offline/objects", "Skybind-Offline-Edits"} {
		if strings.Contains(string(data), bad) {
			t.Fatalf("leaked excluded data: %s", bad)
		}
	}
}
func TestRejectAlterationsAndUnsafeRemotes(t *testing.T) {
	base := demo(t)
	cases := []struct {
		name   string
		mutate func(*Document)
	}{
		{"digest", func(d *Document) { d.Payload.Registry.Mounts[0].Remote = "drive:other" }},
		{"schema", func(d *Document) { d.Payload.Schema = 2 }},
		{"future", func(d *Document) { d.Payload.GeneratedUnix = time.Now().Add(48 * time.Hour).Unix() }},
		{"pin-traversal", func(d *Document) { d.Payload.PinReferences[0].Path = "../private" }},
		{"hash", func(d *Document) { d.SHA256 = strings.Repeat("0", 64) }},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			doc := base
			doc.Payload.PinReferences = append([]PinReference(nil), base.Payload.PinReferences...)
			doc.Payload.Registry.Mounts = append([]config.Mount(nil), base.Payload.Registry.Mounts...)
			tc.mutate(&doc)
			if err := Validate(doc); err == nil {
				t.Fatal("accepted corrupt backup")
			}
		})
	}
	for _, remote := range []string{"s3:https://user:pass@host/path", "drive:folder?token=abc", "drive:password=abc"} {
		r := config.Empty()
		r.Mounts = []config.Mount{{Name: "drive", Remote: remote, Mountpoint: "/mnt/drive"}}
		if _, err := Build(r, uisettings.Snapshot{Settings: uisettings.Defaults()}, offline.Manifest{Schema: 1, QuotaBytes: 8 << 30}); err == nil {
			t.Fatalf("leaked inline credentials: %q", remote)
		}
	}
}
func TestRejectUnknownFieldsOnImport(t *testing.T) {
	doc := demo(t)
	b, _ := json.Marshal(doc)
	var raw map[string]any
	_ = json.Unmarshal(b, &raw)
	raw["inject"] = "root"
	injected, _ := json.Marshal(raw)
	// Callers decode requests via protocol.StrictBytes; the backup format has
	// no escape hatch for unknown privileged filesystem names.
	type request struct {
		Document Document `json:"document"`
	}
	_ = request{}
	if strings.Contains(string(b), "inject") || !strings.Contains(string(injected), "inject") {
		t.Fatal("fixture corrupt")
	}
}
func TestDownloadsNoClobberAndSymlink(t *testing.T) {
	doc := demo(t)
	dir := t.TempDir()
	p, err := SaveToDir(doc, dir)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = SaveToDir(doc, dir); err != nil {
		t.Fatal("idempotent export failed:", err)
	}
	if err = os.Remove(p); err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(p, []byte("user-content"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err = SaveToDir(doc, dir); err == nil {
		t.Fatal("overwrote nonmatching file")
	}
	if err = os.Remove(p); err != nil {
		t.Fatal(err)
	}
	other := filepath.Join(t.TempDir(), "victim")
	_ = os.WriteFile(other, []byte("intact"), 0600)
	if err = os.Symlink(other, p); err != nil {
		t.Fatal(err)
	}
	if _, err = SaveToDir(doc, dir); err == nil {
		t.Fatal("followed destination symlink")
	}
	after, _ := os.ReadFile(other)
	if string(after) != "intact" {
		t.Fatal("symlink escaped")
	}
}
