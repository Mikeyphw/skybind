package main

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"strings"

	"skybind/internal/diagnostics"
	"skybind/internal/mounts/supervisor"
)

// Each scheduled reconciliation is recorded as a fixed-category event.
// Never log raw engine errors, mount names, remote paths, provider stderr,
// credentials or unsanitized lifecycle reasons.
func supervisorAuditEvent(h supervisor.Health) (string, string) {
	reason := "unknown"
	code := "RECONCILE_STATUS"
	switch {
	case h.Reason == "ready" && h.State == "RUNNING":
		reason, code = "ready", "RECONCILE_READY"
	case h.Reason == "explicit_stop":
		reason, code = "explicit_stop", "RECONCILE_STOPPED"
	case h.Reason == "inspection_failed":
		reason, code = "inspection_failed", "RECONCILE_INSPECTION"
	case h.Reason == "retry_budget_exhausted":
		reason, code = "retry_budget_exhausted", "RECONCILE_EXHAUSTED"
	case h.Reason == "backoff":
		reason, code = "backoff", "RECONCILE_BACKOFF"
	case strings.HasPrefix(h.Reason, "start_blocked:"):
		reason, code = "start_blocked", "RECONCILE_ATTEMPT_BLOCKED"
	case h.Attempts > 0:
		reason, code = "start_returned", "RECONCILE_ATTEMPT_RETURNED"
	}
	state := "OTHER"
	switch h.State {
	case "RUNNING", "STOPPED", "RETRYING", "DEGRADED", "STARTING":
		state = h.State
	}
	digest := sha256.Sum256([]byte(h.Name))
	mountHash := hex.EncodeToString(digest[:8])
	// Log bounded categories and numeric retry count; no free-form text.
	if h.Attempts < 0 || h.Attempts > 100000 {
		return "RECONCILE_INVALID", fmt.Sprintf("mount_hash=%s reason=invalid_count", mountHash)
	}
	return code, fmt.Sprintf("mount_hash=%s attempts=%d state=%s reason=%s", mountHash, h.Attempts, state, reason)
}

func writeSupervisorAudit(logs *diagnostics.Store, health []supervisor.Health, reconcileErr error) {
	if logs == nil {
		return
	}
	for _, h := range health {
		code, message := supervisorAuditEvent(h)
		severity := "INFO"
		if code == "RECONCILE_ATTEMPT_BLOCKED" || code == "RECONCILE_EXHAUSTED" || code == "RECONCILE_INSPECTION" {
			severity = "WARN"
		}
		_ = logs.Write(severity, "supervisor", code, message)
	}
	if reconcileErr != nil {
		_ = logs.Write("WARN", "supervisor", "RECONCILE_ERROR", "reason=reconcile_returned_error")
	}
}
