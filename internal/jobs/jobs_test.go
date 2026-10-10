package jobs

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"skybind/internal/mounts/policy"
	"testing"
	"time"
)

type runner struct {
	entered chan struct{}
	done    chan struct{}
}

func (r runner) Execute(ctx context.Context, _ Job) error {
	r.entered <- struct{}{}
	select {
	case <-r.done:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}
func fixture(t *testing.T) (*Store, runner, string) {
	t.Helper()
	dir := filepath.Join(t.TempDir(), "jobs")
	if e := os.Mkdir(dir, 0700); e != nil {
		t.Fatal(e)
	}
	r := runner{make(chan struct{}, 5), make(chan struct{})}
	s, e := Open(dir, r, func() policy.Facts { return policy.Facts{Network: policy.Unknown} })
	if e != nil {
		t.Fatal(e)
	}
	return s, r, dir
}
func registry(kind string) []byte {
	b, _ := json.Marshal(Registry{SchemaVersion: 1, Revision: 0, Jobs: []Job{{Name: "Backup", Kind: kind, Source: "cloud:src", Destination: "store:dst", IntervalSeconds: 300, Enabled: true, NetworkMode: "offline-allowed"}}})
	return b
}
func proof(t *testing.T, result any) string {
	t.Helper()
	m, ok := result.(map[string]any)
	if !ok {
		t.Fatalf("bad proof response: %T", result)
	}
	return m["proof"].(string)
}
func TestTransactionalJobsAndDestructiveProof(t *testing.T) {
	s, r, _ := fixture(t)
	b := registry("sync")
	p, e := s.Preview(b)
	if e != nil {
		t.Fatal(e)
	}
	if !p.(map[string]any)["includes_destructive_sync"].(bool) {
		t.Fatal("sync not identified destructive")
	}
	if _, e = s.Apply(b, "invalid"); e == nil {
		t.Fatal("unconfirmed sync accepted")
	}
	result, e := s.Apply(b, proof(t, p))
	if e != nil {
		t.Fatal(e)
	}
	if result.Revision != 1 {
		t.Fatal("no revision")
	}
	if _, e = s.Apply(b, proof(t, p)); e == nil {
		t.Fatal("replay accepted")
	}
	preview, e := s.RunPreview("Backup")
	if e != nil {
		t.Fatal(e)
	}
	if _, e = s.RunManual("Backup", "invalid"); e == nil {
		t.Fatal("unconfirmed job run")
	}
	run, e := s.RunManual("Backup", proof(t, preview))
	if e != nil {
		t.Fatal(e)
	}
	<-r.entered
	if _, e = s.RunManual("Backup", proof(t, preview)); e == nil {
		t.Fatal("replayed run")
	}
	if _, e = s.Cancel(run.ID); e != nil {
		t.Fatal(e)
	}
	deadline := time.Now().Add(time.Second)
	for time.Now().Before(deadline) {
		v, _ := s.Status()
		for _, item := range v.(map[string]any)["runs"].([]Run) {
			if item.ID == run.ID && item.State == "CANCELLED" {
				return
			}
		}
		time.Sleep(time.Millisecond)
	}
	t.Fatal("cancel did not finish")
}
func TestDurableClaimAndRestartNoDuplicate(t *testing.T) {
	s, r, dir := fixture(t)
	b := registry("copy")
	p, e := s.Preview(b)
	if e != nil {
		t.Fatal(e)
	}
	if _, e = s.Apply(b, proof(t, p)); e != nil {
		t.Fatal(e)
	}
	s.now = func() time.Time { return time.Now().Add(time.Hour) }
	// Job scheduled earlier, so it is due once.
	count, e := s.Tick()
	if e != nil || count != 1 {
		t.Fatalf("due run: %v %v", count, e)
	}
	<-r.entered
	restarted, e := Open(dir, r, func() policy.Facts { return policy.Facts{Network: policy.Unknown} })
	if e != nil {
		t.Fatal(e)
	}
	v, _ := restarted.Status()
	runs := v.(map[string]any)["runs"].([]Run)
	if runs[0].State != "INTERRUPTED" {
		t.Fatalf("restart misreported: %s", runs[0].State)
	}
	count, e = restarted.Tick()
	if e != nil || count != 0 {
		t.Fatal("duplicate restart scheduling")
	}
	close(r.done)
	// Wait for the original executor to finish publishing before TempDir cleanup.
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		v, _ := s.Status()
		complete := true
		for _, item := range v.(map[string]any)["runs"].([]Run) {
			if item.State == "RUNNING" {
				complete = false
			}
		}
		if complete {
			return
		}
		time.Sleep(time.Millisecond)
	}
	t.Fatal("original worker did not exit before fixture teardown")
}
func TestUnsafeJobsFailClosed(t *testing.T) {
	s, _, _ := fixture(t)
	for _, v := range []Job{{Name: "X", Kind: "sync", Source: "local:/etc", Destination: "other:dst"}, {Name: "X", Kind: "execute", Source: "remote:src", Destination: "other:dst"}, {Name: "X", Kind: "copy", Source: "r:../x", Destination: "t:dst"}, {Name: "X", Kind: "copy", Source: "r:src", Destination: "t:dst", IntervalSeconds: 1}} {
		b, _ := json.Marshal(Registry{SchemaVersion: 1, Jobs: []Job{v}})
		if _, e := s.Preview(b); e == nil {
			t.Errorf("unsafe job accepted: %+v", v)
		}
	}
}
func TestManagedJobSchedulingNotSpoofable(t *testing.T) {
	s, _, _ := fixture(t)
	r := registry("copy")
	var item Registry
	if e := json.Unmarshal(r, &item); e != nil {
		t.Fatal(e)
	}
	item.Jobs[0].NextUnix = time.Now().Add(24 * time.Hour).Unix()
	b, _ := json.Marshal(item)
	if _, e := s.Preview(b); e == nil {
		t.Fatal("client spoofed next-run timestamp")
	}
	item.Jobs[0].NextUnix = 0
	item.Jobs[0].LastRunID = "spoof"
	b, _ = json.Marshal(item)
	if _, e := s.Preview(b); e == nil {
		t.Fatal("client spoofed last run")
	}
}
func TestNumericStatsRedactsOtherFields(t *testing.T) {
	b, speed, eta, ok := decodeStats([]byte(`{"stats":{"bytes":44,"speed":3.25,"eta":7,"token":"SECRET"}}`))
	if !ok || b != 44 || speed != 3.25 || eta != 7 {
		t.Fatal("bad safe numeric progress")
	}
	if _, _, _, ok = decodeStats([]byte(`{"stats":{"bytes":-1,"speed":4}}`)); ok {
		t.Fatal("negative progress accepted")
	}
}
