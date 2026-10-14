package jobs

import (
	"context"
	"os"
	"path/filepath"
	"skybind/internal/opevents"
	"testing"
	"time"
)

// A controllable progress source simulates rclone stats without network or mount.
type streamedRunner struct {
	entered  chan struct{}
	released chan struct{}
}

func (r streamedRunner) Execute(ctx context.Context, j Job) error {
	return r.ExecuteWithProgress(ctx, j, nil)
}
func (r streamedRunner) ExecuteWithProgress(ctx context.Context, j Job, cb func(int64, float64, int64)) error {
	if cb != nil {
		cb(1024, 128, 8)
		cb(2048, 256, 4)
	}
	close(r.entered)
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-r.released:
		return nil
	}
}
func TestPhaseAProgressCancelAndRestartReplay(t *testing.T) {
	s, _, dir := fixture(t)
	evDir := filepath.Join(t.TempDir(), "events")
	if err := os.Mkdir(evDir, 0700); err != nil {
		t.Fatal(err)
	}
	events, e := opevents.Open(evDir)
	if e != nil {
		t.Fatal(e)
	}
	r := streamedRunner{make(chan struct{}), make(chan struct{})}
	s.executor = r
	s.SetEventObserver(func(e opevents.Event) {
		if err := events.Append(e); err != nil {
			t.Errorf("event append: %v", err)
		}
	})
	p, e := s.Preview(registry("copy"))
	if e != nil {
		t.Fatal(e)
	}
	if _, e = s.Apply(registry("copy"), proof(t, p)); e != nil {
		t.Fatal(e)
	}
	p, e = s.RunPreview("Backup")
	if e != nil {
		t.Fatal(e)
	}
	run, e := s.RunManual("Backup", proof(t, p))
	if e != nil {
		t.Fatal(e)
	}
	<-r.entered
	if _, e = s.Cancel(run.ID); e != nil {
		t.Fatal(e)
	}
	deadline := time.Now().Add(time.Second * 2)
	for time.Now().Before(deadline) {
		v, _ := s.RunStatus(run.ID)
		if v.State == "CANCELLED" {
			break
		}
		time.Sleep(time.Millisecond * 5)
	}
	latest, _ := s.RunStatus(run.ID)
	if latest.State != "CANCELLED" {
		t.Fatal("job not cancelled", latest)
	}
	ev2, e := opevents.Open(evDir)
	if e != nil {
		t.Fatal(e)
	}
	page, e := ev2.Poll(context.Background(), 0, 64, run.ID, 0)
	if e != nil {
		t.Fatal(e)
	}
	expected := map[string]bool{"job.started": false, "job.progress": false, "job.cancelling": false, "job.cancelled": false}
	for _, it := range page.Events {
		if _, ok := expected[it.Type]; ok {
			expected[it.Type] = true
		}
		if it.Progress != nil && it.Progress.Bytes > 2048 {
			t.Fatal("bad progress")
		}
	}
	for name, seen := range expected {
		if !seen {
			t.Errorf("missing %s: %+v", name, page)
		}
	}
	// Restarting a completed run must not fabricate a new event or relaunch work.
	reopened, e := Open(dir, r, s.facts)
	if e != nil {
		t.Fatal(e)
	}
	v, e := reopened.RunStatus(run.ID)
	if e != nil || v.State != "CANCELLED" {
		t.Fatal("restart state mismatch", e, v)
	}
}
