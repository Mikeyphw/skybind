package support

import (
	"archive/zip"
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func newSupport(t *testing.T) *Store {
	t.Helper()
	dir := filepath.Join(t.TempDir(), "support")
	if e := os.Mkdir(dir, 0700); e != nil {
		t.Fatal(e)
	}
	s, e := Open(dir)
	if e != nil {
		t.Fatal(e)
	}
	return s
}
func TestBundleSafety(t *testing.T) {
	s := newSupport(t)
	meta, e := s.Create(map[string]any{"doctor": map[string]string{"password": "canaryPWD", "authorization": "Bearer canaryAuth", "note": "healthy"}})
	if e != nil {
		t.Fatal(e)
	}
	b, e := s.Read(meta.ID)
	if e != nil {
		t.Fatal(e)
	}
	if strings.Contains(string(b), "canaryPWD") || strings.Contains(string(b), "canaryAuth") {
		t.Fatal("secret leak")
	}
	z, e := zip.NewReader(bytes.NewReader(b), int64(len(b)))
	if e != nil || len(z.File) != 2 {
		t.Fatal(e)
	}
	if _, e = s.Read("../etc/passwd"); e == nil {
		t.Fatal("arbitrary read")
	}
	if e = os.Chmod(filepath.Join(s.dir, meta.ID+".zip"), 0644); e != nil {
		t.Fatal(e)
	}
	if _, e = s.Read(meta.ID); e == nil {
		t.Fatal("weak file accepted")
	}
}
func TestNoSymlinkOrOversize(t *testing.T) {
	s := newSupport(t)
	if _, e := s.Create(map[string]any{"../private": 1}); e == nil {
		t.Fatal("traversal")
	}
	if _, e := s.Create(map[string]any{"huge": strings.Repeat("x", 70000)}); e == nil {
		t.Fatal("oversized content")
	}
	d := filepath.Join(t.TempDir(), "link")
	if e := os.Symlink(s.dir, d); e != nil {
		t.Fatal(e)
	}
	if _, e := Open(d); e == nil {
		t.Fatal("symlink root")
	}
}
