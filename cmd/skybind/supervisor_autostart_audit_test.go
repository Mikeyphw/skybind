package main

import (
	"strings"
	"testing"

	"skybind/internal/mounts/supervisor"
)

func TestAutoStartAuditContainsOnlySafeFailureClass(t *testing.T) {
	code, message := supervisorAuditEvent(supervisor.Health{
		Name: "private-drive", State: "DEGRADED", Reason: "start_blocked:token=S3CRET",
		Attempts: 5, RecoveryProbes: 1, FailureClass: "provider_remote_failure",
	})
	if code != "RECONCILE_ATTEMPT_BLOCKED" || !strings.Contains(message, "failure_class=provider_remote_failure") || !strings.Contains(message, "recovery_probes=1") {
		t.Fatalf("audit lost safe evidence: %q %q", code, message)
	}
	if strings.Contains(message, "private-drive") || strings.Contains(message, "S3CRET") {
		t.Fatal("secrets reached audit")
	}
	code, message = supervisorAuditEvent(supervisor.Health{Name: "private-drive", State: "RETRYING", Reason: "recovery_cooldown", Attempts: 5, RecoveryProbes: 0, FailureClass: "token=BAD"})
	if code != "RECONCILE_RECOVERY_COOLDOWN" || !strings.Contains(message, "failure_class=unknown") || strings.Contains(message, "BAD") {
		t.Fatalf("unsafe cooldown audit: %s %s", code, message)
	}
}
