package uisettings

import (
	"os"
	"path/filepath"
	"testing"
)

func TestSettingsPreviewApplyAndReplay(t *testing.T) {
	d := filepath.Join(t.TempDir(), "private")
	if e := os.Mkdir(d, 0700); e != nil {
		t.Fatal(e)
	}
	s, e := Open(d)
	if e != nil {
		t.Fatal(e)
	}
	v := Defaults()
	v.DefaultView = "settings"
	v.DenseMode = true
	p, e := s.Preview(v)
	if e != nil {
		t.Fatal(e)
	}
	_, e = s.Apply(p.CurrentRevision, v, p.CandidateDigest, "not-a-proof")
	if e == nil {
		t.Fatal("accepted forged proof")
	}
	snap, e := s.Apply(p.CurrentRevision, v, p.CandidateDigest, p.PreviewProof)
	if e != nil {
		t.Fatal(e)
	}
	if snap.Revision != 1 || snap.Settings.DefaultView != "settings" {
		t.Fatal(snap)
	}
	if _, e = s.Apply(p.CurrentRevision, v, p.CandidateDigest, p.PreviewProof); e == nil {
		t.Fatal("replayed proof")
	}
	reload, e := Open(d)
	if e != nil || reload.Snapshot().Settings.DefaultView != "settings" {
		t.Fatalf("lost state: %v", e)
	}
}
func TestInvalidSettingsAndFileLink(t *testing.T) {
	d := filepath.Join(t.TempDir(), "private")
	if e := os.Mkdir(d, 0700); e != nil {
		t.Fatal(e)
	}
	s, e := Open(d)
	if e != nil {
		t.Fatal(e)
	}
	for _, bad := range []Settings{{}, func() Settings { x := Defaults(); x.DefaultView = "../secret"; return x }(), func() Settings { x := Defaults(); x.LogLimit = 10000; return x }()} {
		if _, e = s.Preview(bad); e == nil {
			t.Fatal("accepted invalid settings")
		}
	}
	target := filepath.Join(t.TempDir(), "target")
	if e := os.WriteFile(target, []byte("unchanged"), 0600); e != nil {
		t.Fatal(e)
	}
	if e := os.Symlink(target, filepath.Join(d, fileName)); e != nil {
		t.Fatal(e)
	}
	if _, e = Open(d); e == nil {
		t.Fatal("followed symlink")
	}
}
