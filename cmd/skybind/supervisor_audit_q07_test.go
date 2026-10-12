package main

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"skybind/internal/diagnostics"
	"skybind/internal/mounts/supervisor"
)

func q07Log(t *testing.T) *diagnostics.Store {
	t.Helper()
	dir := filepath.Join(t.TempDir(), "logs")
	if err := os.Mkdir(dir, 0700); err != nil {
		t.Fatal(err)
	}
	store, err := diagnostics.Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	return store
}
func q07Entries(t *testing.T, s *diagnostics.Store) []diagnostics.Entry {
	t.Helper()
	entries, err := s.Query(diagnostics.Filter{Source: "supervisor", Limit: 200})
	if err != nil {
		t.Fatal(err)
	}
	return entries
}
func TestQ07HealthyLogDedupAndHeartbeat(t *testing.T) {
	store := q07Log(t)
	audit := newSupervisorAuditor()
	now := time.Now()
	audit.now = func() time.Time { return now }
	healthy := []supervisor.Health{{Name: "sensitive-mount", State: "RUNNING", Reason: "ready"}}
	for i := 0; i < 50; i++ {
		audit.Write(store, healthy, nil)
		now = now.Add(30 * time.Second)
	}
	entries := q07Entries(t, store)
	if len(entries) != 1 || entries[0].Code != "RECONCILE_READY" {
		t.Fatalf("50 repeated healthy ticks: %+v", entries)
	}
	now = now.Add(31 * time.Minute)
	audit.Write(store, healthy, nil)
	entries = q07Entries(t, store)
	if len(entries) != 2 || entries[1].Code != "RECONCILE_READY" {
		t.Fatalf("periodic heartbeat missing: %+v", entries)
	}
	for _, e := range entries {
		if strings.Contains(e.Message, "sensitive-mount") {
			t.Fatal("mount name leaked")
		}
	}
}
func TestQ07SignificantTransitionsAndErrors(t *testing.T) {
	store := q07Log(t)
	audit := newSupervisorAuditor()
	now := time.Now()
	audit.now = func() time.Time { return now }
	audit.Write(store, []supervisor.Health{{Name: "cloud", State: "RETRYING", Reason: "policy_deferred"}}, nil)
	audit.Write(store, []supervisor.Health{{Name: "cloud", State: "RETRYING", Reason: "policy_deferred"}}, nil)
	audit.Write(store, []supervisor.Health{{Name: "cloud", State: "DEGRADED", Reason: "start_blocked:token=ultra-secret", Attempts: 1}}, nil)
	audit.Write(store, []supervisor.Health{{Name: "cloud", State: "DEGRADED", Reason: "start_blocked:token=ultra-secret", Attempts: 2}}, nil)
	audit.Write(store, []supervisor.Health{{Name: "cloud", State: "RUNNING", Reason: "ready"}}, nil)
	audit.Write(store, []supervisor.Health{{Name: "cloud", State: "RUNNING", Reason: "ready"}}, nil)
	audit.Write(store, nil, errors.New("token=ultra-secret"))
	audit.Write(store, nil, errors.New("token=ultra-secret"))
	audit.Write(store, nil, nil)
	entries := q07Entries(t, store)
	want := []string{"RECONCILE_POLICY_DEFERRED", "RECONCILE_ATTEMPT_BLOCKED", "RECONCILE_ATTEMPT_BLOCKED", "RECONCILE_RECOVERED", "RECONCILE_ERROR", "RECONCILE_ERROR_CLEARED"}
	if len(entries) != len(want) {
		t.Fatalf("got %d want %d: %+v", len(entries), len(want), entries)
	}
	for i, e := range entries {
		if e.Code != want[i] {
			t.Fatalf("event %d = %s want %s", i, e.Code, want[i])
		}
		if strings.Contains(e.Message, "cloud") || strings.Contains(e.Message, "ultra-secret") {
			t.Fatalf("secret leaked: %+v", e)
		}
	}
}

func TestQ07PolicyDeferredBackoffDoesNotFlood(t *testing.T) {
	store := q07Log(t)
	audit := newSupervisorAuditor()
	now := time.Now()
	audit.now = func() time.Time { return now }
	for i := 0; i < 48; i++ {
		reason := "policy_deferred"
		if i%2 != 0 {
			reason = "backoff"
		}
		audit.Write(store, []supervisor.Health{{Name: "cloud", State: "RETRYING", Reason: reason, Attempts: 0}}, nil)
		now = now.Add(30 * time.Second)
	}
	entries := q07Entries(t, store)
	if len(entries) != 1 || entries[0].Code != "RECONCILE_POLICY_DEFERRED" {
		t.Fatalf("policy/backoff spam: %+v", entries)
	}
}
