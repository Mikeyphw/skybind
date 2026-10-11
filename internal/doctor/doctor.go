// Package doctor reports observable platform checks without inventing device readiness.
package doctor

import (
	"context"
	"os"
	"path/filepath"
	"skybind/internal/diagnostics"
	"skybind/internal/mounts/config"
	"skybind/internal/paths"
	"skybind/internal/rootmgr"
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
		"platform": func(context.Context) (string, string) {
			v, err := rootmgr.CanonicalDetector{}.Status()
			if err != nil {
				return "FAIL", "root_manager_inspection_failed"
			}
			if !v.Root {
				return "WARN", "root_privilege_unavailable"
			}
			if !v.ModulePresent {
				return "WARN", "skybind_module_absent"
			}
			if !v.Confirmed {
				return "WARN", "root_manager_unconfirmed"
			}
			return "INFO", "manager_present_device_not_qualified"
		},
		"namespace": func(context.Context) (string, string) {
			if _, err := os.Readlink("/proc/self/ns/mnt"); err != nil {
				return "WARN", "namespace_inspection_unavailable"
			}
			return "INFO", "namespace_inspectable_exact_app_visibility_not_qualified"
		},
		"mounts": func(context.Context) (string, string) {
			path := filepath.Join(paths.StateRoot, "config", config.RegistryName)
			b, err := os.ReadFile(path)
			if os.IsNotExist(err) {
				return "INFO", "no_mount_registry"
			}
			if err != nil || len(b) > 1<<20 {
				return "WARN", "mount_registry_unreadable"
			}
			registry, e := config.Validate(b)
			if e != nil {
				return "FAIL", "mount_registry_invalid"
			}
			if len(registry.Mounts) == 0 {
				return "INFO", "no_mounts_configured"
			}
			return "INFO", "mount_registry_valid_health_requires_owned_mount_probe"
		},
		"jobs": func(context.Context) (string, string) {
			return inspectPrivateFile(filepath.Join(paths.StateRoot, "jobs", "jobs-v1.json"), "job_registry")
		},
		"rc": func(context.Context) (string, string) {
			return inspectPrivateDirectory(filepath.Join(paths.StateRoot, "rc"), "rc_state")
		},
		"remotes": func(context.Context) (string, string) {
			return inspectPrivateFile(paths.RcloneConfig, "remote_configuration")
		},
		"webui": func(context.Context) (string, string) {
			if _, err := os.Stat(filepath.Join(paths.ModuleRoot, "webroot", "index.html")); err != nil {
				return "WARN", "webui_assets_unavailable"
			}
			return "INFO", "webui_assets_present_auth_and_browser_not_qualified"
		},
	}}
}

// Presence checks never read or return secrets and never claim a live session.
func inspectPrivateFile(path, noun string) (string, string) {
	st, err := os.Lstat(path)
	if os.IsNotExist(err) {
		return "INFO", noun + "_not_configured"
	}
	if err != nil || !st.Mode().IsRegular() || st.Mode().Perm()&0077 != 0 {
		return "FAIL", noun + "_unsafe_or_unreadable"
	}
	return "INFO", noun + "_present_not_execution_qualified"
}
func inspectPrivateDirectory(path, noun string) (string, string) {
	st, err := os.Lstat(path)
	if os.IsNotExist(err) {
		return "INFO", noun + "_not_initialized"
	}
	if err != nil || !st.IsDir() || st.Mode().Perm()&0077 != 0 {
		return "FAIL", noun + "_unsafe_or_unreadable"
	}
	return "INFO", noun + "_private_state_present_not_live_qualified"
}
