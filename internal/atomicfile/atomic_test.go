package atomicfile

import (
	"errors"
	"os"
	"path/filepath"
	"testing"
)

func private(t *testing.T) string {
	t.Helper()
	p := filepath.Join(t.TempDir(), "private")
	if err := os.Mkdir(p, 0700); err != nil {
		t.Fatal(err)
	}
	return p
}
func TestAtomicWriteAndRead(t *testing.T) {
	dir := private(t)
	if err := Write(dir, "state.json", []byte("old")); err != nil {
		t.Fatal(err)
	}
	if err := Write(dir, "state.json", []byte("new")); err != nil {
		t.Fatal(err)
	}
	data, err := Read(dir, "state.json", 128)
	if err != nil || string(data) != "new" {
		t.Fatalf("%q %v", data, err)
	}
	entries, err := os.ReadDir(dir)
	if err != nil || len(entries) != 1 {
		t.Fatalf("staging files leaked: %v %v", entries, err)
	}
}
func TestInterruptedWritePreservesOld(t *testing.T) {
	dir := private(t)
	if err := Write(dir, "record", []byte("old")); err != nil {
		t.Fatal(err)
	}
	err := writeWithHook(dir, "record", []byte("new"), func() error { return errors.New("injected failure") })
	if err == nil {
		t.Fatal("expected interruption")
	}
	b, err := Read(dir, "record", 8)
	if err != nil || string(b) != "old" {
		t.Fatalf("partial publish: %q %v", b, err)
	}
	e, _ := os.ReadDir(dir)
	if len(e) != 1 {
		t.Fatal("temporary file remains")
	}
}
func TestRejectSymlinkAndWeakSecrets(t *testing.T) {
	dir := private(t)
	other := filepath.Join(t.TempDir(), "outside")
	if err := os.WriteFile(other, []byte("keep"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(other, filepath.Join(dir, "record")); err != nil {
		t.Fatal(err)
	}
	if err := Write(dir, "record", []byte("bad")); err == nil {
		t.Fatal("symlink replaced")
	}
	b, _ := os.ReadFile(other)
	if string(b) != "keep" {
		t.Fatal("outside modified")
	}
	os.Remove(filepath.Join(dir, "record"))
	secret := filepath.Join(dir, "record")
	if err := os.WriteFile(secret, []byte("old"), 0600); err != nil {
		t.Fatal(err)
	}
	// File creation permissions are restricted by umask; chmod and verify
	// explicitly so this test exercises a genuinely world-readable secret
	// even under Termux's typical umask 077.
	if err := os.Chmod(secret, 0644); err != nil {
		t.Fatal(err)
	}
	st, err := os.Stat(secret)
	if err != nil {
		t.Fatal(err)
	}
	if st.Mode().Perm() != 0644 {
		t.Fatalf("weak-secret fixture has mode %04o, need 0644", st.Mode().Perm())
	}
	if err := Write(dir, "record", []byte("bad")); err == nil {
		t.Fatal("permissive target accepted")
	}
	if got, err := os.ReadFile(secret); err != nil || string(got) != "old" {
		t.Fatalf("unsafe destination was changed: %q, %v", got, err)
	}
}
func TestRejectInvalidNames(t *testing.T) {
	dir := private(t)
	for _, n := range []string{"", ".", "..", "../target", "foo/bar", "foo\\bar"} {
		if err := Write(dir, n, []byte("x")); err == nil {
			t.Fatalf("accepted %q", n)
		}
	}
}
func TestRejectBadDirectoryModeAndReadLimit(t *testing.T) {
	dir := private(t)
	if err := Write(dir, "record", []byte("large")); err != nil {
		t.Fatal(err)
	}
	if _, err := Read(dir, "record", 2); err == nil {
		t.Fatal("oversized read accepted")
	}
	if err := os.Chmod(dir, 0755); err != nil {
		t.Fatal(err)
	}
	if err := Write(dir, "second", []byte("x")); err == nil {
		t.Fatal("unsafe directory accepted")
	}
}

// Atomic publication must also work when Android provides only search
// permission on an intermediate parent (e.g. the Termux /data/data path).
func TestAtomicThroughSearchOnlyAncestor(t *testing.T) {
	outer := filepath.Join(t.TempDir(), "search-only")
	if err := os.Mkdir(outer, 0700); err != nil {
		t.Fatal(err)
	}
	parent := filepath.Join(outer, "readable")
	if err := os.Mkdir(parent, 0700); err != nil {
		t.Fatal(err)
	}
	dir := filepath.Join(parent, "private")
	if err := os.Mkdir(dir, 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(outer, 0111); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { os.Chmod(outer, 0700) })
	if err := Write(dir, "record", []byte("contents")); err != nil {
		t.Fatal(err)
	}
	b, err := Read(dir, "record", 64)
	if err != nil || string(b) != "contents" {
		t.Fatalf("read: %q %v", b, err)
	}
}
