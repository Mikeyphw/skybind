package config

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func fixture(t *testing.T) *Store {
	t.Helper()
	d := filepath.Join(t.TempDir(), "private")
	if e := os.Mkdir(d, 0700); e != nil {
		t.Fatal(e)
	}
	s, e := Open(d)
	if e != nil {
		t.Fatal(e)
	}
	return s
}
func raw(r Registry) []byte { b, _ := json.Marshal(r); return b }
func TestStaleProofRollback(t *testing.T) {
	s := fixture(t)
	a := Empty()
	a.Mounts = []Mount{{Name: "cloud", Remote: "cloud:/data", Mountpoint: "/storage/emulated/0/Cloud", Enabled: true}}
	p, e := s.Preview(raw(a))
	if e != nil {
		t.Fatal(e)
	}
	old, e := s.Apply(raw(a), p.Token)
	if e != nil || old.Revision != 1 {
		t.Fatalf("publish %v %+v", e, old)
	}
	if _, e = s.Apply(raw(a), p.Token); e == nil {
		t.Fatal("replay accepted")
	}
	if _, e = s.Preview(raw(a)); e == nil {
		t.Fatal("stale accepted")
	}
	b := old
	b.Mounts[0].ChargingOnly = true
	q, e := s.Preview(raw(b))
	if e != nil {
		t.Fatal(e)
	}
	if len(q.Effects) != 1 || q.Effects[0].Restart {
		t.Fatal("policy-only incorrectly restarts")
	}
	n, e := s.Apply(raw(b), q.Token)
	if e != nil || n.Revision != 2 {
		t.Fatal(e)
	}
	rp, e := s.RollbackPreview()
	if e != nil {
		t.Fatal(e)
	}
	back, e := s.Rollback(rp.Token)
	if e != nil || back.Revision != 3 || back.Mounts[0].ChargingOnly {
		t.Fatalf("bad rollback: %+v %v", back, e)
	}
}
func TestBadInputAndOverlap(t *testing.T) {
	r := Empty()
	r.Mounts = []Mount{{Name: "a", Remote: "a:/", Mountpoint: "/storage/emulated/0/foo"}, {Name: "b", Remote: "a:/", Mountpoint: "/storage/emulated/0/foo/bar"}}
	if _, e := Validate(raw(r)); e == nil {
		t.Fatal("overlap accepted")
	}
	for _, bad := range [][]byte{[]byte(`{"schema_version":2,"revision":0,"mounts":[],"args_file":"/tmp/shell"}`), []byte(`{"schema_version":2,"revision":0,"mounts":[{"name":"x","remote":"a:/","mountpoint":"/data/adb/skybind"}]}`), []byte(`{"schema_version":2,"revision":0,"mounts":[{"name":"x","remote":"a:/","mountpoint":"/storage/../etc"}]}`)} {
		if _, e := Validate(bad); e == nil {
			t.Errorf("accepted unsafe candidate %s", bad)
		}
	}
}
func TestInterruptedCommitRevertsCoherently(t *testing.T) {
	s := fixture(t)
	r := Empty()
	r.Mounts = []Mount{{Name: "a", Remote: "a:/", Mountpoint: "/mnt/test/a"}}
	p, e := s.Preview(raw(r))
	if e != nil {
		t.Fatal(e)
	}
	old, _ := s.Apply(raw(r), p.Token)
	if old.Revision != 1 {
		t.Fatal(e)
	}
	previous, _ := s.Previous()
	intent, _ := json.Marshal(struct {
		Before   Registry `json:"before"`
		Previous Registry `json:"previous"`
	}{old, previous})
	if e = os.WriteFile(filepath.Join(s.dir, PendingName), intent, 0600); e != nil {
		t.Fatal(e)
	}
	if e = s.write(RegistryName, Registry{SchemaVersion: 2, Revision: 2, Mounts: []Mount{}}); e != nil {
		t.Fatal(e)
	}
	recovered, e := Open(s.dir)
	if e != nil {
		t.Fatal(e)
	}
	got, e := recovered.Snapshot()
	if e != nil || got.Revision != 1 || len(got.Mounts) != 1 {
		t.Fatalf("crash recovery failed %+v %v", got, e)
	}
}
