package paths

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestCanonicalNoOverrides(t *testing.T) {
	t.Setenv("SKYBIND_ROOT", "/tmp/evil")
	t.Setenv("HOME", "/tmp/root")
	if Default().State != StateRoot || Default().Engine != Engine {
		t.Fatal("configuration override accepted")
	}
	if Default().Socket != DaemonSocket {
		t.Fatal("socket mismatch")
	}
}
func TestChildTraversalRejected(t *testing.T) {
	for _, v := range []string{"", ".", "../config", "foo/../bar", "foo//bar", "/etc/passwd", "foo/./bar", "foo\\bar"} {
		if _, err := Child(v); err == nil {
			t.Errorf("accepted %q", v)
		}
	}
	if got, err := Child("run/trace"); err != nil || got != StateRoot+"/run/trace" {
		t.Fatalf("got %s, %v", got, err)
	}
}
func TestSecureStatePaths(t *testing.T) {
	root := filepath.Join(t.TempDir(), "state")
	owner := uint32(os.Geteuid())
	if err := ensureAt(root, []string{"config", "config/previous", "run"}, owner); err != nil {
		t.Fatal(err)
	}
	for _, p := range []string{root, filepath.Join(root, "config"), filepath.Join(root, "config/previous"), filepath.Join(root, "run")} {
		st, err := os.Stat(p)
		if err != nil {
			t.Fatal(err)
		}
		if st.Mode().Perm() != 0700 {
			t.Fatalf("unsafe mode %s %s", p, st.Mode())
		}
	}
}
func TestSymlinkedRootRejected(t *testing.T) {
	parent := t.TempDir()
	real := filepath.Join(parent, "real")
	if err := os.Mkdir(real, 0700); err != nil {
		t.Fatal(err)
	}
	link := filepath.Join(parent, "state")
	if err := os.Symlink(real, link); err != nil {
		t.Fatal(err)
	}
	if err := ensureAt(link, []string{"config"}, uint32(os.Geteuid())); err == nil {
		t.Fatal("symlink accepted")
	}
}
func TestWeakPermissionsRejected(t *testing.T) {
	parent := t.TempDir()
	root := filepath.Join(parent, "state")
	if err := os.Mkdir(root, 0700); err != nil {
		t.Fatal(err)
	}
	// A restrictive process umask (077 on Termux) masks requested mkdir
	// permissions. Explicitly change the mode so this negative test proves
	// the private-path validator rejects an *actually* permissive directory.
	if err := os.Chmod(root, 0755); err != nil {
		t.Fatal(err)
	}
	st, err := os.Stat(root)
	if err != nil {
		t.Fatal(err)
	}
	if st.Mode().Perm() != 0755 {
		t.Fatalf("weak-directory fixture has mode %04o, need 0755", st.Mode().Perm())
	}
	if err := ensureAt(root, []string{"config"}, uint32(os.Geteuid())); err == nil {
		t.Fatal("permissive private root accepted")
	}
}
func TestDirectorySymlinkRejected(t *testing.T) {
	parent := t.TempDir()
	root := filepath.Join(parent, "state")
	if err := ensureAt(root, nil, uint32(os.Geteuid())); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink("/etc", filepath.Join(root, "config")); err != nil {
		t.Fatal(err)
	}
	if err := ensureAt(root, []string{"config"}, uint32(os.Geteuid())); err == nil {
		t.Fatal("symlinked child accepted")
	}
}
func TestRelativeInputsMustBeClean(t *testing.T) {
	for _, p := range []string{"./a", "/tmp/../tmp/foo", "foo"} {
		if err := ensureAt(p, nil, uint32(os.Geteuid())); err == nil {
			t.Fatalf("accepted %s", p)
		}
	}
	if !strings.HasPrefix(RcloneConfig, StateRoot+"/") {
		t.Fatal("rclone config escapes state")
	}
}

// Regression: Android/Termux can traverse an ancestor without permission to
// read its directory entries (notably /data/data). Opening every ancestor
// with O_RDONLY caused EACCES despite the private destination being writable.
func TestSearchOnlyAncestor(t *testing.T) {
	ancestor := filepath.Join(t.TempDir(), "search-only")
	if err := os.Mkdir(ancestor, 0700); err != nil {
		t.Fatal(err)
	}
	privateParent := filepath.Join(ancestor, "owned")
	if err := os.Mkdir(privateParent, 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(ancestor, 0111); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { os.Chmod(ancestor, 0700) })
	root := filepath.Join(privateParent, "state")
	if err := ensureAt(root, []string{"config", "run"}, uint32(os.Geteuid())); err != nil {
		t.Fatalf("search-only ancestor should be traversable: %v", err)
	}
	if _, err := OpenVerifiedDirectory(root); err != nil {
		t.Fatalf("private leaf not readable: %v", err)
	}
}

func TestSymlinkedIntermediateRejected(t *testing.T) {
	parent := t.TempDir()
	real := filepath.Join(parent, "real")
	if err := os.Mkdir(real, 0700); err != nil {
		t.Fatal(err)
	}
	link := filepath.Join(parent, "link")
	if err := os.Symlink(real, link); err != nil {
		t.Fatal(err)
	}
	if err := ensureAt(filepath.Join(link, "state"), nil, uint32(os.Geteuid())); err == nil {
		t.Fatal("symlinked ancestor accepted")
	}
}
