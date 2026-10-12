package main

import (
	"strings"
	"testing"

	"skybind/internal/mounts/supervisor"
)

func TestSupervisorAuditOnlyFixedCategories(t *testing.T) {
	samples := []struct {
		reason, state string
		attempts      int
		want          string
	}{
		{"ready", "RUNNING", 0, "RECONCILE_READY"},
		{"backoff", "RETRYING", 2, "RECONCILE_BACKOFF"},
		{"retry_budget_exhausted", "DEGRADED", 5, "RECONCILE_EXHAUSTED"},
		{"start_blocked:token=my-secret", "DEGRADED", 2, "RECONCILE_ATTEMPT_BLOCKED"},
		{"provider stderr secret", "BROKEN secret", 2, "RECONCILE_ATTEMPT_RETURNED"},
	}
	for _, sample := range samples {
		code, message := supervisorAuditEvent(supervisor.Health{Name: "cloud", Reason: sample.reason, State: sample.state, Attempts: sample.attempts})
		if code != sample.want {
			t.Errorf("code=%s want=%s", code, sample.want)
		}
		if strings.Contains(message, "secret") || strings.Contains(message, "cloud") || strings.Contains(message, "token") {
			t.Errorf("unsafe audit: %s", message)
		}
		if !strings.Contains(message, "mount_hash=") || !strings.Contains(message, "attempts=") {
			t.Errorf("insufficient audit: %s", message)
		}
	}
}
