package supervisor

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"testing"
	"time"

	"skybind/internal/mounts/lifecycle"
)

type q07Engine struct {
	nowError error
	desired  bool
	running  bool
	starts   int
}

func (f *q07Engine) List() ([]string, error) { return []string{"cloud"}, nil }
func (f *q07Engine) Status(string) (lifecycle.State, error) {
	if f.running {
		return lifecycle.State{Observed: "RUNNING"}, nil
	}
	return lifecycle.State{Observed: "STOPPED"}, nil
}
func (f *q07Engine) Desired(string) (bool, error) { return f.desired, nil }
func (f *q07Engine) Start(string) (lifecycle.State, error) {
	f.starts++
	if f.nowError != nil {
		return lifecycle.State{}, f.nowError
	}
	f.running = true
	return lifecycle.State{Observed: "RUNNING"}, nil
}
func TestQ07PolicyDeferredDoesNotSpendAttempts(t *testing.T) {
	f := &q07Engine{desired: true, nowError: lifecycle.ErrResourcePolicyDeferred}
	s := New(f)
	clock := time.Now()
	s.now = func() time.Time { return clock }
	for i := 0; i < 18; i++ { // >5, across nine minutes of blocked facts
		result, err := s.Reconcile(context.Background())
		if err != nil {
			t.Fatal(err)
		}
		if len(result) != 1 || result[0].Reason != "policy_deferred" || result[0].Attempts != 0 {
			t.Fatalf("deferred %d: %+v", i, result)
		}
		clock = clock.Add(30 * time.Second)
	}
	if f.starts != 18 || s.retry["cloud"].attempts != 0 {
		t.Fatalf("pre-spawn policy denied counted as real failures: %+v", s.retry)
	}
	f.nowError = nil
	result, err := s.Reconcile(context.Background())
	if err != nil || result[0].State != "RUNNING" {
		t.Fatalf("blocked recovery: %+v %v", result, err)
	}
	result, err = s.Reconcile(context.Background())
	if err != nil || result[0].Attempts != 0 || s.retry["cloud"].attempts != 0 {
		t.Fatalf("healthy retry budget not cleared %+v", result)
	}
}
func TestQ07BudgetPersistsAcrossPolicyDeferAndDaemonRestart(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "health")
	if err := os.Mkdir(dir, 0700); err != nil {
		t.Fatal(err)
	}
	f := &q07Engine{desired: true, nowError: errors.New("provider failed")}
	s, err := NewPersistent(f, dir)
	if err != nil {
		t.Fatal(err)
	}
	clock := time.Now()
	s.now = func() time.Time { return clock }
	_, err = s.Reconcile(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if s.retry["cloud"].attempts != 1 {
		t.Fatal("real failure not charged")
	}
	f.nowError = errors.Join(lifecycle.ErrResourcePolicyDeferred, errors.New("network not ready"))
	clock = clock.Add(time.Minute)
	for i := 0; i < 8; i++ {
		result, err := s.Reconcile(context.Background())
		if err != nil {
			t.Fatal(err)
		}
		if result[0].Attempts != 1 {
			t.Fatalf("lost or consumed retry budget: %+v", result[0])
		}
		clock = clock.Add(time.Minute)
	}
	after, err := NewPersistent(f, dir)
	if err != nil {
		t.Fatal(err)
	}
	if after.retry["cloud"].attempts != 1 {
		t.Fatalf("retry budget lost after reboot: %+v", after.retry)
	}
	after.now = func() time.Time { return clock }
	f.nowError = errors.New("persistent failure")
	for i := 0; i < 40; i++ {
		_, err = after.Reconcile(context.Background())
		if err != nil {
			t.Fatal(err)
		}
		clock = clock.Add(time.Minute)
	}
	if after.retry["cloud"].attempts != 5 || after.retry["cloud"].probes != 2 || f.starts != 15 { // 1 real + 8 deferred + 4 real + 2 delayed probes
		t.Fatalf("hard failures must stop after 5+2 bounded starts; attempts=%+v starts=%d", after.retry, f.starts)
	}
}
func TestQ07ExplicitStopRemainsStopped(t *testing.T) {
	f := &q07Engine{desired: false, nowError: lifecycle.ErrResourcePolicyDeferred}
	s := New(f)
	for i := 0; i < 12; i++ {
		if _, err := s.Reconcile(context.Background()); err != nil {
			t.Fatal(err)
		}
	}
	if f.starts != 0 {
		t.Fatal("explicitly stopped mount was started")
	}
}
