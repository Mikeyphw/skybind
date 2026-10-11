package supervisor

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"skybind/internal/mounts/lifecycle"
	"testing"
	"time"
)

type fake struct {
	desired bool
	calls   int
	status  lifecycle.State
	failure bool
}

func (f *fake) List() ([]string, error)                { return []string{"cloud"}, nil }
func (f *fake) Status(string) (lifecycle.State, error) { return f.status, nil }
func (f *fake) Desired(string) (bool, error)           { return f.desired, nil }
func (f *fake) Start(string) (lifecycle.State, error) {
	f.calls++
	if f.failure {
		return f.status, errors.New("offline")
	}
	return lifecycle.State{Name: "cloud", Observed: "RUNNING"}, nil
}
func TestStoppedNeverRestarted(t *testing.T) {
	f := &fake{desired: false}
	s := New(f)
	for i := 0; i < 4; i++ {
		s.Reconcile(context.Background())
	}
	if f.calls != 0 {
		t.Fatal("explicit stop restarted")
	}
}
func TestFailureBounded(t *testing.T) {
	f := &fake{desired: true, failure: true}
	s := New(f)
	clock := time.Now()
	s.now = func() time.Time { return clock }
	for i := 0; i < 20; i++ {
		s.Reconcile(context.Background())
		clock = clock.Add(2 * time.Minute)
	}
	if f.calls != 5 {
		t.Fatalf("unbounded retries %d", f.calls)
	}
}
func TestHealthyNoRestart(t *testing.T) {
	f := &fake{desired: true, status: lifecycle.State{Observed: "RUNNING"}}
	s := New(f)
	s.Reconcile(context.Background())
	if f.calls != 0 {
		t.Fatal("healthy mount restarted")
	}
}
func TestRetryBudgetPersisted(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "health")
	if e := os.Mkdir(dir, 0700); e != nil {
		t.Fatal(e)
	}
	f := &fake{desired: true, failure: true}
	s, e := NewPersistent(f, dir)
	if e != nil {
		t.Fatal(e)
	}
	s.Reconcile(context.Background())
	next, e := NewPersistent(f, dir)
	if e != nil {
		t.Fatal(e)
	}
	if next.retry["cloud"].attempts != 1 {
		t.Fatal("retry budget lost on restart")
	}
}
