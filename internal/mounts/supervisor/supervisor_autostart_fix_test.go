package supervisor

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"skybind/internal/mounts/lifecycle"
)

func TestAutoStartRecoveryProbesPersistAndStop(t *testing.T) {
	f := &q07Engine{desired: true, nowError: errors.New("provider network unavailable; secret_token=should-not-leak")}
	dir := filepath.Join(t.TempDir(), "health")
	if err := os.MkdirAll(dir, 0700); err != nil {
		t.Fatal(err)
	}
	s, err := NewPersistent(f, dir)
	if err != nil {
		t.Fatal(err)
	}
	clock := time.Date(2026, 10, 14, 1, 0, 0, 0, time.UTC)
	s.now = func() time.Time { return clock }
	for i := 0; i < 5; i++ {
		h, e := s.Reconcile(context.Background())
		if e != nil {
			t.Fatal(e)
		}
		if h[0].FailureClass != "start_error_other" || strings.Contains(h[0].Reason, "secret_token") {
			t.Fatalf("unsafe health %+v", h)
		}
		clock = clock.Add(time.Minute)
	}
	if f.starts != 5 {
		t.Fatal(f.starts)
	}
	h, _ := s.Reconcile(context.Background())
	if h[0].Reason != "recovery_cooldown" || h[0].RecoveryProbes != 0 {
		t.Fatalf("missing first cooldown: %+v", h)
	}
	if s.NetworkChanged() {
		t.Fatal("network hint expedited exhausted failure")
	}
	// Reinitialize from canonical state and prove restart never erases budget.
	after, err := NewPersistent(f, dir)
	if err != nil {
		t.Fatal(err)
	}
	after.now = func() time.Time { return clock }
	// Fifth failure was at original clock + 4min; delay until +9min.
	clock = clock.Add(4 * time.Minute)
	h, err = after.Reconcile(context.Background())
	if err != nil || f.starts != 6 || h[0].RecoveryProbes != 1 {
		t.Fatalf("missing first delayed probe %+v %v starts=%d", h, err, f.starts)
	}
	clock = clock.Add(time.Minute)
	if after.NetworkChanged() {
		t.Fatal("network hint expedited probe backoff")
	}
	h, _ = after.Reconcile(context.Background())
	if f.starts != 6 || h[0].Reason != "recovery_cooldown" {
		t.Fatalf("probe ran early %+v", h)
	}
	after2, err := NewPersistent(f, dir)
	if err != nil {
		t.Fatal(err)
	}
	after2.now = func() time.Time { return clock }
	clock = clock.Add(15 * time.Minute)
	h, err = after2.Reconcile(context.Background())
	if err != nil || f.starts != 7 || h[0].RecoveryProbes != 2 {
		t.Fatalf("missing second delayed probe %+v %v starts=%d", h, err, f.starts)
	}
	clock = clock.Add(24 * time.Hour)
	for i := 0; i < 10; i++ {
		h, err = after2.Reconcile(context.Background())
		if err != nil || h[0].Reason != "retry_budget_exhausted" {
			t.Fatalf("exhaustion not durable: %+v %v", h, err)
		}
	}
	if f.starts != 7 {
		t.Fatalf("unbounded attempts: %d", f.starts)
	}
	// Observing a legitimately running mount clears *both* budgets.
	f.running = true
	h, err = after2.Reconcile(context.Background())
	if err != nil || h[0].Reason != "ready" || len(after2.retry) != 0 {
		t.Fatalf("healthy mount did not clear retries: %+v %v", h, err)
	}
	f.running = false
	f.nowError = nil
	h, err = after2.Reconcile(context.Background())
	if err != nil || h[0].State != "RUNNING" {
		t.Fatalf("healthy reconnection prevented: %+v %v", h, err)
	}
}

func TestAutostartRecoveryPolicyAndExplicitStop(t *testing.T) {
	f := &q07Engine{desired: true, nowError: errors.New("temporary")}
	s := New(f)
	clock := time.Now()
	s.now = func() time.Time { return clock }
	for i := 0; i < 5; i++ {
		if _, err := s.Reconcile(context.Background()); err != nil {
			t.Fatal(err)
		}
		clock = clock.Add(time.Minute)
	}
	f.nowError = lifecycle.ErrResourcePolicyDeferred
	clock = clock.Add(10 * time.Minute)
	h, err := s.Reconcile(context.Background())
	if err != nil || h[0].Reason != "policy_deferred" || h[0].RecoveryProbes != 0 {
		t.Fatalf("policy denial spent probe %+v %v", h, err)
	}
	if s.NetworkChanged() {
		t.Fatal("policy cannot accelerate exhausted recovery budget")
	}
	f.desired = false
	h, err = s.Reconcile(context.Background())
	if err != nil || h[0].Reason != "explicit_stop" || len(s.retry) != 0 {
		t.Fatalf("explicit stop failed %+v %v", h, err)
	}
	f.desired = true
	f.nowError = nil
	h, err = s.Reconcile(context.Background())
	if err != nil || h[0].State != "RUNNING" {
		t.Fatalf("fresh desired true cannot start %+v %v", h, err)
	}
}

func TestAutostartFailureClassesSanitized(t *testing.T) {
	for _, tc := range []struct{ message, category string }{
		{"FUSE readiness/mount identity not observed (provider_remote_failure)", "provider_remote_failure"},
		{"FUSE readiness/mount identity not observed (provider_stderr_unclassified)", "provider_stderr_unclassified"},
		{"could not prove child process ownership", "child_identity_unverified"},
		{"auth token=S3cret unrecognized", "start_error_other"},
	} {
		if got := classifyStartFailure(errors.New(tc.message)); got != tc.category {
			t.Errorf("%s != %s", got, tc.category)
		}
	}
	if validFailureClass("token=bad") {
		t.Fatal("untrusted persisted category accepted")
	}
}

func TestAutoStartLegacyRetryStateAndCorruption(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "health")
	if err := os.Mkdir(dir, 0700); err != nil {
		t.Fatal(err)
	}
	// Legacy retry-v1 schema had no recovery_probes or failure_class fields.
	legacy := []byte(`{"cloud":{"attempts":5,"next":"2026-10-13T00:00:00Z"}}`)
	if err := os.WriteFile(filepath.Join(dir, "retry-v1.json"), legacy, 0600); err != nil {
		t.Fatal(err)
	}
	f := &q07Engine{desired: true, nowError: errors.New("still offline")}
	s, err := NewPersistent(f, dir)
	if err != nil {
		t.Fatalf("backward incompatible: %v", err)
	}
	if s.retry["cloud"].attempts != 5 || s.retry["cloud"].probes != 0 {
		t.Fatal("lost historic budget")
	}
	s.now = func() time.Time { return time.Date(2026, 10, 14, 0, 0, 0, 0, time.UTC) }
	h, err := s.Reconcile(context.Background())
	if err != nil || len(h) != 1 || h[0].RecoveryProbes != 1 {
		t.Fatalf("old exhausted state should receive only a bounded new probe %+v %v", h, err)
	}
	// Unknown free-form categories must fail closed, not permit forged log labels.
	invalid := []byte(`{"cloud":{"attempts":5,"recovery_probes":2,"failure_class":"token=secret"}}`)
	if err := os.WriteFile(filepath.Join(dir, "retry-v1.json"), invalid, 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := NewPersistent(f, dir); err == nil {
		t.Fatal("unsafe retry state accepted")
	}
}
