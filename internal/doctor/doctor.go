// Package doctor reports observable platform checks without inventing device readiness.
package doctor

import (
	"context"
	"os"
	"skybind/internal/diagnostics"
	"skybind/internal/paths"
	"skybind/internal/runtimeauth"
)

type Check struct {
	ID     string `json:"id"`
	Status string `json:"status"`
	Reason string `json:"reason"`
	Remedy string `json:"remedy"`
}
type Report struct {
	SchemaVersion int     `json:"schema_version"`
	Qualification string  `json:"qualification"`
	Checks        []Check `json:"checks"`
}
type Probe func(context.Context) (string, string)
type Reporter struct{ Probes map[string]Probe }

func (r Reporter) Run(ctx context.Context) Report {
	ids := []string{"runtime", "fuse", "platform", "mounts", "namespace", "jobs", "rc", "remotes", "storage", "webui"}
	result := Report{SchemaVersion: 1, Qualification: "SOURCE_ONLY_DEVICE_NOT_ATTESTED", Checks: make([]Check, 0, len(ids))}
	for _, id := range ids {
		probe := r.Probes[id]
		status, reason := "WARN", "not_inspected"
		if probe != nil {
			status, reason = probe(ctx)
		}
		if status != "PASS" && status != "INFO" && status != "WARN" && status != "FAIL" {
			status = "FAIL"
			reason = "invalid_probe"
		}
		result.Checks = append(result.Checks, Check{ID: id, Status: status, Reason: diagnostics.Redact(reason), Remedy: remedy(id, status)})
	}
	return result
}
func remedy(id, status string) string {
	if status == "PASS" || status == "INFO" {
		return "none"
	}
	switch id {
	case "runtime", "fuse":
		return "verify_pinned_runtime_integrity"
	case "namespace":
		return "inspect_exact_android_app_visibility"
	case "storage":
		return "verify_private_storage_permissions"
	case "webui":
		return "verify_loopback_or_embedded_transport"
	default:
		return "inspect_related_subsystem_and_logs"
	}
}
func Canonical() Reporter {
	return Reporter{Probes: map[string]Probe{
		"runtime": func(context.Context) (string, string) {
			s := runtimeauth.StatusCanonical()
			if s.Ready {
				return "PASS", "verified_runtime"
			}
			return "FAIL", "runtime_integrity_unverified"
		},
		"fuse": func(context.Context) (string, string) {
			if _, e := os.Lstat(paths.FuseHelper); e != nil {
				return "WARN", "fuse_helper_unavailable"
			}
			return "INFO", "fuse_presence_not_device_qualified"
		},
		"storage": func(context.Context) (string, string) {
			s, e := os.Lstat(paths.StateRoot)
			if e != nil || !s.IsDir() || s.Mode().Perm() != 0700 {
				return "FAIL", "private_state_unavailable"
			}
			return "PASS", "private_state_mode_verified"
		},
		"platform":  func(context.Context) (string, string) { return "INFO", "device_not_qualified" },
		"namespace": func(context.Context) (string, string) { return "WARN", "app_visibility_not_device_qualified" },
		"webui":     func(context.Context) (string, string) { return "INFO", "transport_requires_live_probe" },
	}}
}
