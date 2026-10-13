package offline

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"
)

type blockingRunner struct {
	started chan struct{}
	once    sync.Once
}

func (r *blockingRunner) Run(ctx context.Context, args ...string) ([]byte, error) {
	if len(args) > 0 && args[0] == "copyto" {
		r.once.Do(func() { close(r.started) })
		<-ctx.Done()
		return nil, ctx.Err()
	}
	return nil, errors.New("blocked metadata")
}
func waitTask(t *testing.T, m *TaskManager, id string) TaskStatus {
	t.Helper()
	until := time.Now().Add(2 * time.Second)
	for time.Now().Before(until) {
		for _, task := range m.Tasks() {
			if task.ID == id && task.State != "RUNNING" {
				return task
			}
		}
		time.Sleep(5 * time.Millisecond)
	}
	t.Fatal("offline task stuck")
	return TaskStatus{}
}
func TestM05UIAsyncPinCompletion(t *testing.T) {
	s, _ := fixture(t)
	m := NewTaskManager(s)
	task, err := m.Start("pin", "drive", "report.txt")
	if err != nil {
		t.Fatal(err)
	}
	out := waitTask(t, m, task.ID)
	if out.State != "SUCCEEDED" || out.Pinned != 1 {
		t.Fatalf("bad task: %+v", out)
	}
	if m.Busy() {
		t.Fatal("task still marked busy")
	}
	status, err := s.Status(context.Background(), "drive", "report.txt", false)
	if err != nil || status.State != "AVAILABLE_OFFLINE" {
		t.Fatalf("pin not durable: %+v, %v", status, err)
	}
}
func TestM05UIRejectsInvalidTasks(t *testing.T) {
	s, _ := fixture(t)
	m := NewTaskManager(s)
	for _, q := range []struct{ kind, mount, path string }{{"shell", "drive", "a"}, {"pin", "/dev", "a"}, {"pin", "drive", "a/../evil"}, {"export", "drive", "/root"}} {
		if _, err := m.Start(q.kind, q.mount, q.path); err == nil {
			t.Fatalf("accepted invalid task %+v", q)
		}
	}
}
func TestM05UICancelledPinDoesNotPublish(t *testing.T) {
	s, _ := fixture(t)
	r := &blockingRunner{started: make(chan struct{})}
	// Metadata is intentionally unavailable; this may fail before copy begins.
	// A cancel request may only succeed while the task is RUNNING.
	s.r = r
	m := NewTaskManager(s)
	task, err := m.Start("pin", "drive", "report.txt")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := m.Start("pin", "drive", "report.txt"); err == nil {
		t.Fatal("allowed parallel task")
	}
	if err := m.Cancel(task.ID); err != nil {
		t.Fatal(err)
	}
	out := waitTask(t, m, task.ID)
	if out.State != "CANCELLED" {
		t.Fatalf("cancel misreported %+v", out)
	}
	manifest, err := s.List()
	if err != nil || len(manifest.Pins) != 0 {
		t.Fatalf("cancel published pin: %+v %v", manifest, err)
	}
}
