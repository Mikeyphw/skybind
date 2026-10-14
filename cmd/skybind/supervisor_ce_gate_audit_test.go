package main

import (
	"skybind/internal/mounts/supervisor"
	"strings"
	"testing"
)

func TestSupervisorCEStorageDeferredAuditIsSanitized(t *testing.T) {
	code, msg := supervisorAuditEvent(supervisor.Health{Name: "user supplied private mount", State: "RETRYING", Reason: "android_storage_deferred", Attempts: 0})
	if code != "RECONCILE_STORAGE_DEFERRED" || !strings.Contains(msg, "reason=android_storage_deferred") || strings.Contains(msg, "user supplied private") {
		t.Fatalf("incorrect audit: %s %s", code, msg)
	}
}
