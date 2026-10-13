package offline

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestPublishOfflineViewIndependentOfRemote(t *testing.T) {
	s, f := fixture(t)
	f.listing = []RemoteFile{{Path: "a.txt", Size: 5}, {Path: "b.txt", Size: 4}}
	if n, e := s.Pin(context.Background(), "drive", "docs", true); e != nil || n != 2 {
		t.Fatalf("pin: %d %v", n, e)
	}
	f.files = map[string]string{} // remote unavailable: publish must not access provider
	root := filepath.Join(t.TempDir(), "views")
	if e := os.Mkdir(root, 0700); e != nil {
		t.Fatal(e)
	}
	v, e := s.publishViewAt(context.Background(), "drive", root)
	if e != nil {
		t.Fatal(e)
	}
	if !strings.HasPrefix(v, filepath.Join(root, "drive", "snapshot-")) {
		t.Fatalf("bad view path %s", v)
	}
	for _, file := range []struct{ path, body string }{{"docs/a.txt", "alpha"}, {"docs/b.txt", "beta"}} {
		data, e := os.ReadFile(filepath.Join(v, file.path))
		if e != nil || string(data) != file.body {
			t.Fatalf("view file %s %q %v", file.path, data, e)
		}
	}
	private, e := s.Status(context.Background(), "drive", "docs/a.txt", false)
	if e != nil || private.State != "AVAILABLE_OFFLINE" {
		t.Fatalf("pin changed: %+v %v", private, e)
	}
	other, e := s.publishViewAt(context.Background(), "drive", root)
	if e != nil || other == v {
		t.Fatalf("overwrote a published view %q %q %v", v, other, e)
	}
}
func TestPublishOfflineViewCorruptPinFailsWithoutPublicOutput(t *testing.T) {
	s, _ := fixture(t)
	if _, e := s.Pin(context.Background(), "drive", "report.txt", false); e != nil {
		t.Fatal(e)
	}
	m, e := s.List()
	if e != nil {
		t.Fatal(e)
	}
	obj := filepath.Join(s.dir, "objects", m.Pins[0].SHA256)
	if e := os.WriteFile(obj, []byte("corrupt"), 0600); e != nil {
		t.Fatal(e)
	}
	root := filepath.Join(t.TempDir(), "views")
	if e := os.Mkdir(root, 0700); e != nil {
		t.Fatal(e)
	}
	if _, e := s.publishViewAt(context.Background(), "drive", root); e == nil {
		t.Fatal("published corrupt pin")
	}
	entries, e := os.ReadDir(root)
	if e != nil || len(entries) != 0 {
		t.Fatalf("left public output %+v %v", entries, e)
	}
}
func TestPublishOfflineViewStaleAndCancellationFailClosed(t *testing.T) {
	s, _ := fixture(t)
	if _, e := s.Pin(context.Background(), "drive", "report.txt", false); e != nil {
		t.Fatal(e)
	}
	root := filepath.Join(t.TempDir(), "views")
	if e := os.Mkdir(root, 0700); e != nil {
		t.Fatal(e)
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, e := s.publishViewAt(ctx, "drive", root); !errors.Is(e, context.Canceled) {
		t.Fatalf("cancellation: %v", e)
	}
	m, e := s.List()
	if e != nil {
		t.Fatal(e)
	}
	m.Pins[0].RemoteIdentity = hex.EncodeToString(sha256.New().Sum(make([]byte, 0))) // intentionally wrong 32-byte hash
	release, e := s.lock()
	if e != nil {
		t.Fatal(e)
	}
	e = s.save(m)
	release()
	if e != nil {
		t.Fatal(e)
	}
	if _, e := s.publishViewAt(context.Background(), "drive", root); e == nil {
		t.Fatal("published stale remote identity")
	}
	entries, e := os.ReadDir(root)
	if e != nil || len(entries) != 0 {
		t.Fatalf("left public output %+v %v", entries, e)
	}
}
func TestPublishOfflineViewRejectsSymlinkDestination(t *testing.T) {
	s, _ := fixture(t)
	if _, e := s.Pin(context.Background(), "drive", "report.txt", false); e != nil {
		t.Fatal(e)
	}
	parent := t.TempDir()
	root := filepath.Join(parent, "views")
	if e := os.Symlink(t.TempDir(), root); e != nil {
		t.Fatal(e)
	}
	if _, e := s.publishViewAt(context.Background(), "drive", root); e == nil {
		t.Fatal("followed output root symlink")
	}
}
