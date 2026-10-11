package rootmgr

import (
	"os"
	"path/filepath"
	"testing"
)

func TestRootManagerIsCapabilityEvidenceNotGuess(t *testing.T) {
	d := t.TempDir()
	s, e := Detect(d, true)
	if e != nil || s.Confirmed || s.Manager != "unknown" || s.DeviceQualified {
		t.Fatal(s, e)
	}
	_ = os.Mkdir(filepath.Join(d, "magisk"), 0700)
	s, _ = Detect(d, true)
	if !s.Confirmed || s.Manager != "Magisk" {
		t.Fatal(s)
	}
	_ = os.Mkdir(filepath.Join(d, "ksu"), 0700)
	s, _ = Detect(d, true)
	if s.Confirmed || s.Manager != "ambiguous" {
		t.Fatal("ambiguous manager claimed confirmed")
	}
}
