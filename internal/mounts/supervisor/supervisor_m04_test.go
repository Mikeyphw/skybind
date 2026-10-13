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

func TestM04NetworkHintOnlyExpeditesPolicyDeferral(t *testing.T) {
	clock := time.Now()
	f := &q07Engine{desired: true, nowError: lifecycle.ErrResourcePolicyDeferred}
	s := New(f)
	s.now = func() time.Time { return clock }
	health, err := s.Reconcile(context.Background())
	if err != nil || health[0].Reason != "policy_deferred" {
		t.Fatalf("initial: %+v %v", health, err)
	}
	if !s.NetworkChanged() {
		t.Fatal("policy deferral not expedited")
	}
	if s.retry["cloud"].attempts != 0 || s.retry["cloud"].next != clock {
		t.Fatal("expedition consumed tokens")
	}
	clock = clock.Add(time.Second)
	if s.NetworkChanged() {
		t.Fatal("network event storm not throttled")
	}
	f.nowError = nil
	health, err = s.Reconcile(context.Background())
	if err != nil || health[0].State != "RUNNING" {
		t.Fatalf("ready mount should recover: %+v %v", health, err)
	}
	if s.NetworkChanged() {
		t.Fatal("healthy mount expedited")
	}
}
func TestM04RealFailureBudgetCannotBeBypassed(t *testing.T) {
	clock := time.Now()
	f := &q07Engine{desired: true, nowError: errors.New("provider offline")}
	s := New(f)
	s.now = func() time.Time { return clock }
	_, err := s.Reconcile(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	due := s.retry["cloud"].next
	for i := 0; i < 20; i++ {
		if s.NetworkChanged() {
			t.Fatal("real failure expedited")
		}
	}
	if s.retry["cloud"].next != due || s.retry["cloud"].attempts != 1 {
		t.Fatal("real failure backoff changed")
	}
}
func TestM04DeferredStateSurvivesRestart(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "health")
	if err := os.Mkdir(dir, 0700); err != nil {
		t.Fatal(err)
	}
	f := &q07Engine{desired: true, nowError: lifecycle.ErrResourcePolicyDeferred}
	s, err := NewPersistent(f, dir)
	if err != nil {
		t.Fatal(err)
	}
	clock := time.Now()
	s.now = func() time.Time { return clock }
	if _, err = s.Reconcile(context.Background()); err != nil {
		t.Fatal(err)
	}
	recovered, err := NewPersistent(f, dir)
	if err != nil {
		t.Fatal(err)
	}
	recovered.now = func() time.Time { return clock }
	if !recovered.retry["cloud"].deferred || !recovered.NetworkChanged() {
		t.Fatal("persisted policy wait could not be expedited")
	}
	if recovered.retry["cloud"].attempts != 0 {
		t.Fatal("budget mutated")
	}
}
func TestM04ExplicitStopNeverStartsOnNetworkHint(t *testing.T) {
	f := &q07Engine{desired: false}
	s := New(f)
	if s.NetworkChanged() {
		t.Fatal("stopped mount received expedited attempt")
	}
	if _, err := s.Reconcile(context.Background()); err != nil {
		t.Fatal(err)
	}
	if f.starts != 0 {
		t.Fatal("explicit stop undone")
	}
}
