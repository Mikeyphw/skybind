package cache

import (
	"os"
	"path/filepath"
	"testing"
)

func fixture(t *testing.T) (*Manager, string) {
	t.Helper()
	root := filepath.Join(t.TempDir(), "cache")
	if e := os.Mkdir(root, 0700); e != nil {
		t.Fatal(e)
	}
	if e := os.Mkdir(filepath.Join(root, "cloud"), 0700); e != nil {
		t.Fatal(e)
	}
	return newManager(root, func(string) bool { return false }), filepath.Join(root, "cloud")
}
func TestClearPreservesUnverifiedCache(t *testing.T) {
	m, dir := fixture(t)
	file := filepath.Join(dir, "dirty-pending-upload")
	if err := os.WriteFile(file, []byte("queued"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := m.Preview("cloud", "clear", 0); err == nil {
		t.Fatal("unknown cache allowed destructive preview")
	}
	if _, err := m.Apply("cloud", "clear", "forged", 0); err == nil {
		t.Fatal("unknown cache allowed destructive apply")
	}
	if b, err := os.ReadFile(file); err != nil || string(b) != "queued" {
		t.Fatal("dirty file lost")
	}
}
func TestEmptyCachePreviewReplay(t *testing.T) {
	m, _ := fixture(t)
	v, err := m.Preview("cloud", "clear", 0)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = m.Apply("cloud", "clear", v.Proof, 0); err != nil {
		t.Fatal(err)
	}
	if _, err = m.Apply("cloud", "clear", v.Proof, 0); err == nil {
		t.Fatal("replay accepted")
	}
}
func TestSymlinkFailsClosed(t *testing.T) {
	m, dir := fixture(t)
	outside := filepath.Join(t.TempDir(), "secret")
	os.WriteFile(outside, []byte("sensitive"), 0600)
	os.Symlink(outside, filepath.Join(dir, "link"))
	if _, e := m.Preview("cloud", "clear", 0); e == nil {
		t.Fatal("symlink accepted")
	}
	if b, _ := os.ReadFile(outside); string(b) != "sensitive" {
		t.Fatal("outside modified")
	}
}
func TestRunningCacheProtected(t *testing.T) {
	m, dir := fixture(t)
	m.running = func(string) bool { return true }
	os.WriteFile(filepath.Join(dir, "a"), []byte("x"), 0600)
	if _, e := m.Preview("cloud", "forget", 0); e == nil {
		t.Fatal("running cache exposed")
	}
}
func TestUnknownFileCannotBeClearedAfterPreview(t *testing.T) {
	m, dir := fixture(t)
	proof, e := m.Preview("cloud", "clear", 0)
	if e != nil {
		t.Fatal(e)
	}
	file := filepath.Join(dir, "new-dirty-upload")
	os.WriteFile(file, []byte("queued"), 0600)
	if _, e = m.Apply("cloud", "clear", proof.Proof, 0); e == nil {
		t.Fatal("stale proof allowed deletion")
	}
	if _, e = os.Stat(file); e != nil {
		t.Fatal("dirty file removed")
	}
}
func TestForgetPreservesNestedDirtyFile(t *testing.T) {
	m, dir := fixture(t)
	nested := filepath.Join(dir, "nested")
	os.Mkdir(nested, 0700)
	file := filepath.Join(nested, "dirty")
	os.WriteFile(file, []byte("x"), 0600)
	if _, err := m.Preview("cloud", "forget", 0); err == nil {
		t.Fatal("forget accepted unknown writes")
	}
	if _, err := os.Stat(file); err != nil {
		t.Fatal("dirty file removed")
	}
}
func TestAutoPrunePreservesUnverifiedWrites(t *testing.T) {
	m, dir := fixture(t)
	for i := 0; i < 4; i++ {
		if e := os.WriteFile(filepath.Join(dir, string(rune('a'+i))), []byte("abcde"), 0600); e != nil {
			t.Fatal(e)
		}
	}
	snap, err := m.AutoPruneStopped("cloud", 20, 75, 25)
	if err == nil || snap.Bytes != 20 {
		t.Fatalf("unknown dirty cache was pruned: %+v %v", snap, err)
	}
}
