package support

import (
	"crypto/sha256"
	"encoding/hex"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestSupportExportVerifiedAndNoOverwrite(t *testing.T) {
	private := filepath.Join(t.TempDir(), "support")
	if err := os.Mkdir(private, 0700); err != nil {
		t.Fatal(err)
	}
	s, err := Open(private)
	if err != nil {
		t.Fatal(err)
	}
	meta, err := s.Create(map[string]any{"doctor": map[string]any{"status": "PASS"}})
	if err != nil {
		t.Fatal(err)
	}
	downloads := filepath.Join(t.TempDir(), "Download")
	if err := os.Mkdir(downloads, 0755); err != nil {
		t.Fatal(err)
	}
	out, err := s.exportToDir(meta.ID, meta.SHA256, downloads)
	if err != nil {
		t.Fatal(err)
	}
	if filepath.Base(out) != "skybind-support-"+meta.ID+".zip" {
		t.Fatalf("unexpected output %s", out)
	}
	b, err := os.ReadFile(out)
	if err != nil {
		t.Fatal(err)
	}
	h := sha256.Sum256(b)
	if hex.EncodeToString(h[:]) != meta.SHA256 {
		t.Fatal("export changed payload")
	}
	if retry, err := s.exportToDir(meta.ID, meta.SHA256, downloads); err != nil || retry != out {
		t.Fatalf("idempotent retry %q %v", retry, err)
	}
	for _, tc := range []struct{ id, digest string }{
		{"../../etc/passwd", meta.SHA256}, {meta.ID, strings.Repeat("f", 64)}, {meta.ID, "not-a-digest"},
	} {
		if _, err := s.exportToDir(tc.id, tc.digest, downloads); err == nil {
			t.Fatal("accepted invalid export")
		}
	}
	if err := os.Remove(out); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(out, []byte("not a bundle"), 0644); err != nil {
		t.Fatal(err)
	}
	if _, err := s.exportToDir(meta.ID, meta.SHA256, downloads); err == nil {
		t.Fatal("overwrote alien file")
	}
	if err := os.Remove(out); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(filepath.Join(private, meta.ID+".zip"), out); err != nil {
		t.Fatal(err)
	}
	if _, err := s.exportToDir(meta.ID, meta.SHA256, downloads); err == nil {
		t.Fatal("followed hostile public symlink")
	}
}

func TestSupportExportNoSymlinkedDownloads(t *testing.T) {
	p := filepath.Join(t.TempDir(), "support")
	if err := os.Mkdir(p, 0700); err != nil {
		t.Fatal(err)
	}
	s, err := Open(p)
	if err != nil {
		t.Fatal(err)
	}
	meta, err := s.Create(map[string]any{"status": "healthy"})
	if err != nil {
		t.Fatal(err)
	}
	root := t.TempDir()
	if err := os.Symlink(root, filepath.Join(root, "Download")); err != nil {
		t.Fatal(err)
	}
	if _, err := s.exportToDir(meta.ID, meta.SHA256, filepath.Join(root, "Download")); err == nil {
		t.Fatal("followed Downloads directory symlink")
	}
}
