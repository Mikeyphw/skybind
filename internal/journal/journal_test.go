package journal

import (
	"os"
	"path/filepath"
	"testing"
)

func TestCrashRecoveryOwnership(t *testing.T) {
	d := filepath.Join(t.TempDir(), "j")
	if e := os.Mkdir(d, 0700); e != nil {
		t.Fatal(e)
	}
	j, e := Open(d)
	if e != nil {
		t.Fatal(e)
	}
	r, e := j.Start("config.apply")
	if e != nil {
		t.Fatal(e)
	}
	again, e := Open(d)
	if e != nil {
		t.Fatal(e)
	}
	got, e := again.Get(r.ID)
	if e != nil || got.State != Interrupted {
		t.Fatalf("not interrupted: %+v %v", got, e)
	}
	r.State = Succeeded
	if e = again.Update(r); e == nil {
		t.Fatal("recovered operation mutated")
	}
	n, e := again.Start("config.apply")
	if e != nil {
		t.Fatal(e)
	}
	n.Cancellable = false
	n.State = Cancelled
	if e = again.Update(n); e == nil {
		t.Fatal("unsafe cancellation")
	}
}
