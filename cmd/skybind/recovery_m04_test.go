package main

import (
	"context"
	"errors"
	"skybind/internal/mounts/lifecycle"
	"skybind/internal/mounts/supervisor"
	"testing"
	"time"
)

func TestM04AdaptiveRecoveryCadence(t *testing.T) {
	healthy := []supervisor.Health{{State: "RUNNING", Reason: "ready"}, {State: "STOPPED", Reason: "explicit_stop"}}
	if recoveryInterval(healthy, nil) != 90*time.Second {
		t.Fatal("healthy cadence")
	}
	cases := [][]supervisor.Health{
		{{State: "RETRYING", Reason: "policy_deferred"}},
		{{State: "DEGRADED", Reason: "retry_budget_exhausted"}},
		{{State: "RUNNING", Reason: "ready"}, {State: "RETRYING", Reason: "backoff"}},
	}
	for _, v := range cases {
		if recoveryInterval(v, nil) != 30*time.Second {
			t.Fatalf("pending cadence: %+v", v)
		}
	}
	if recoveryInterval(nil, nil) != recoveryHealthy {
		t.Fatal("empty registry should be idle")
	}
	if recoveryInterval(healthy, errors.New("unavailable")) != 30*time.Second {
		t.Fatal("error cadence")
	}
}

// Event-driven recovery is exercised without kernel permissions or long sleeps.
// The authenticated policy/Start decision remains the source of truth.
type m04Engine struct {
	calls       chan struct{}
	statusCalls chan struct{}
	desired     bool
	err         error
}

func (e *m04Engine) List() ([]string, error) { return []string{"cloud"}, nil }
func (e *m04Engine) Status(string) (lifecycle.State, error) {
	if e.statusCalls != nil {
		select {
		case e.statusCalls <- struct{}{}:
		default:
		}
	}
	return lifecycle.State{Observed: "STOPPED"}, nil
}
func (e *m04Engine) Desired(string) (bool, error) { return e.desired, nil }
func (e *m04Engine) Start(string) (lifecycle.State, error) {
	e.calls <- struct{}{}
	return lifecycle.State{Observed: "STOPPED"}, e.err
}
func TestM04EventWakeAndCancel(t *testing.T) {
	engine := &m04Engine{calls: make(chan struct{}, 3), desired: true, err: lifecycle.ErrResourcePolicyDeferred}
	ctx, cancel := context.WithCancel(context.Background())
	changes := make(chan struct{}, 2)
	sup := supervisor.New(engine)
	done := make(chan struct{})
	go func() {
		defer close(done)
		runRecoveryLoopWithTiming(ctx, sup, nil, nil, changes, recoveryTiming{
			initial: 3 * time.Millisecond, pending: 400 * time.Millisecond, healthy: 500 * time.Millisecond,
			eventDelay: 6 * time.Millisecond, eventThrottle: 25 * time.Millisecond, jobInterval: 250 * time.Millisecond,
		})
	}()
	defer cancel()
	select {
	case <-engine.calls:
	case <-time.After(200 * time.Millisecond):
		t.Fatal("initial recovery missing")
	}
	changes <- struct{}{}
	select {
	case <-engine.calls:
	case <-time.After(200 * time.Millisecond):
		t.Fatal("event did not expedite a policy-deferred mount")
	}
	cancel()
	select {
	case <-done:
	case <-time.After(200 * time.Millisecond):
		t.Fatal("recovery loop did not stop")
	}
}

func TestM04PeriodicFallbackWithoutNetlink(t *testing.T) {
	engine := &m04Engine{calls: make(chan struct{}, 4), statusCalls: make(chan struct{}, 4), desired: true, err: lifecycle.ErrResourcePolicyDeferred}
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() {
		defer close(done)
		runRecoveryLoopWithTiming(ctx, supervisor.New(engine), nil, nil, nil, recoveryTiming{
			initial: 2 * time.Millisecond, pending: 18 * time.Millisecond, healthy: 80 * time.Millisecond,
			eventDelay: 3 * time.Millisecond, eventThrottle: 25 * time.Millisecond, jobInterval: 80 * time.Millisecond,
		})
	}()
	defer cancel()
	for i := 0; i < 2; i++ {
		select {
		case <-engine.statusCalls:
		case <-time.After(150 * time.Millisecond):
			t.Fatal("timer fallback did not run")
		}
	}
	cancel()
	select {
	case <-done:
	case <-time.After(150 * time.Millisecond):
		t.Fatal("fallback did not terminate")
	}
}
