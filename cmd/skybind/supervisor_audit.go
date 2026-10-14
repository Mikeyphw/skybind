package main

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"strings"
	"time"

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
	case h.Reason == "policy_deferred":
		reason, code = "policy_deferred", "RECONCILE_POLICY_DEFERRED"
	case h.Reason == "android_storage_deferred":
		reason, code = "android_storage_deferred", "RECONCILE_STORAGE_DEFERRED"
	case h.Reason == "recovery_cooldown":
		reason, code = "recovery_cooldown", "RECONCILE_RECOVERY_COOLDOWN"
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
	// All extra fields are fixed tokens or bounded integers. Do not trust
	// unknown FailureClass strings even if another caller constructs Health.
	class := "unknown"
	if supervisor.AllowedFailureClass(h.FailureClass) && h.FailureClass != "" {
		class = h.FailureClass
	}
	probes := h.RecoveryProbes
	if probes < 0 || probes > 2 {
		return "RECONCILE_INVALID", fmt.Sprintf("mount_hash=%s reason=invalid_count", mountHash)
	}
	return code, fmt.Sprintf("mount_hash=%s attempts=%d recovery_probes=%d state=%s reason=%s failure_class=%s", mountHash, h.Attempts, probes, state, reason, class)
}

// supervisorAuditor is owned by the reconciliation goroutine; it retains only
// hashed mount identities and sanitized output. Ordinary healthy
// ticks do not erase meaningful failures from the bounded diagnostic store.
// A periodic heartbeat preserves evidence of a healthy long-running daemon.
const supervisorAuditHeartbeat = 30 * time.Minute

type auditEntry struct {
	code, message string
	attempts      int
	recorded      time.Time
}
type supervisorAuditor struct {
	now      func() time.Time
	previous map[string]auditEntry
	hadError bool
}

func newSupervisorAuditor() *supervisorAuditor {
	return &supervisorAuditor{now: time.Now, previous: make(map[string]auditEntry)}
}

func (a *supervisorAuditor) Write(logs *diagnostics.Store, health []supervisor.Health, reconcileErr error) {
	if logs == nil {
		return
	}
	current := make(map[string]struct{}, len(health))
	for _, h := range health {
		code, message := supervisorAuditEvent(h)
		// Stable SHA-256 mount identifier, never the mount name. Reuse the
		// sanitized message as the key: it already contains the identifier.
		key := fmt.Sprintf("%x", sha256.Sum256([]byte(h.Name)))
		current[key] = struct{}{}
		prev, known := a.previous[key]
		// A backoff tick without a new attempt is still the same policy
		// deferral. Do not alternate between DEFERRED and BACKOFF every tick.
		if known && prev.code == "RECONCILE_POLICY_DEFERRED" && code == "RECONCILE_BACKOFF" && prev.attempts == h.Attempts && a.now().Sub(prev.recorded) < supervisorAuditHeartbeat {
			continue
		}
		if known && prev.code == code && prev.message == message && a.now().Sub(prev.recorded) < supervisorAuditHeartbeat {
			continue
		}
		if known && prev.code != "RECONCILE_READY" && code == "RECONCILE_READY" {
			code = "RECONCILE_RECOVERED"
		}
		severity := "INFO"
		switch code {
		case "RECONCILE_ATTEMPT_BLOCKED", "RECONCILE_EXHAUSTED", "RECONCILE_INSPECTION":
			severity = "WARN"
		}
		if err := logs.Write(severity, "supervisor", code, message); err == nil {
			// Preserve original category for comparisons, not the recovered
			// presentation code; next tick stays quiet.
			category, _ := supervisorAuditEvent(h)
			a.previous[key] = auditEntry{code: category, message: message, attempts: h.Attempts, recorded: a.now()}
		}
	}
	if reconcileErr == nil {
		for key := range a.previous {
			if _, present := current[key]; !present {
				delete(a.previous, key)
			}
		}
	}
	if reconcileErr != nil && !a.hadError {
		_ = logs.Write("WARN", "supervisor", "RECONCILE_ERROR", "reason=reconcile_returned_error")
	}
	if reconcileErr == nil && a.hadError {
		_ = logs.Write("INFO", "supervisor", "RECONCILE_ERROR_CLEARED", "reason=reconcile_resumed")
	}
	a.hadError = reconcileErr != nil
}
