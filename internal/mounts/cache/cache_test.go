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
func TestClearAndReplay(t *testing.T) {
	m, dir := fixture(t)
	if e := os.WriteFile(filepath.Join(dir, "file"), []byte("hello"), 0600); e != nil {
		t.Fatal(e)
	}
	p, e := m.Preview("cloud", "clear", 0)
	if e != nil || p.BytesToRemove != 5 {
		t.Fatal(p, e)
	}
	v, e := m.Apply("cloud", "clear", p.Proof, 0)
	if e != nil || v.Bytes != 0 {
		t.Fatal(v, e)
	}
	if _, e = m.Apply("cloud", "clear", p.Proof, 0); e == nil {
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
func TestMutationBetweenPreviewAndApply(t *testing.T) {
	m, dir := fixture(t)
	file := filepath.Join(dir, "one")
	os.WriteFile(file, []byte("one"), 0600)
	p, e := m.Preview("cloud", "clear", 0)
	if e != nil {
		t.Fatal(e)
	}
	os.WriteFile(file, []byte("changed"), 0600)
	if _, e = m.Apply("cloud", "clear", p.Proof, 0); e == nil {
		t.Fatal("stale proof accepted")
	}
}
func TestForgetRemovesNestedDirs(t *testing.T) {
	m, dir := fixture(t)
	nested := filepath.Join(dir, "nested")
	if e := os.Mkdir(nested, 0700); e != nil {
		t.Fatal(e)
	}
	if e := os.WriteFile(filepath.Join(nested, "cachepart"), []byte("x"), 0600); e != nil {
		t.Fatal(e)
	}
	p, e := m.Preview("cloud", "forget", 0)
	if e != nil {
		t.Fatal(e)
	}
	_, e = m.Apply("cloud", "forget", p.Proof, 0)
	if e != nil {
		t.Fatal(e)
	}
	if _, e = os.Stat(nested); !os.IsNotExist(e) {
		t.Fatalf("nested directory not reset: %v", e)
	}
}
func TestAutoPruneLowWater(t *testing.T) {
	m, dir := fixture(t)
	for i := 0; i < 4; i++ {
		if e := os.WriteFile(filepath.Join(dir, string(rune('a'+i))), []byte("abcde"), 0600); e != nil {
			t.Fatal(e)
		}
	}
	s, e := m.AutoPruneStopped("cloud", 20, 75, 25)
	if e != nil || s.Bytes > 5 {
		t.Fatalf("low-water pruning failed %+v %v", s, e)
	}
}
