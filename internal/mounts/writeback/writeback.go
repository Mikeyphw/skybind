// Package writeback interprets only the sanitized VFS writeback counters.
// Missing or malformed counters are UNKNOWN, never a safe zero.
package writeback

import (
	"encoding/json"
	"errors"
	"math"
)

type Snapshot struct {
	Mount  string `json:"mount"`
	State  string `json:"state"` // idle, busy, errored, unknown
	Queued int64  `json:"uploads_queued"`
	Active int64  `json:"uploads_in_progress"`
	Errors int64  `json:"errored_files"`
	InUse  int64  `json:"in_use"`
	Reason string `json:"reason"` // closed vocabulary, no paths/names
	Source string `json:"source"`
}

func Unknown(name, reason string) Snapshot {
	return Snapshot{Mount: name, State: "unknown", Reason: reason, Source: "authenticated_vfs_stats"}
}
func (s Snapshot) Safe() bool {
	return s.State == "idle" && s.Queued == 0 && s.Active == 0 && s.Errors == 0
}

func counter(v any) (int64, bool) {
	n, ok := v.(float64)
	if !ok || math.IsNaN(n) || math.IsInf(n, 0) || n < 0 || n > 1e12 || math.Trunc(n) != n {
		return 0, false
	}
	return int64(n), true
}

// ParseVFS never includes filesystem paths, remote names, option maps or RC errors.
// rclone versions that do not expose upload counters remain UNKNOWN.
func ParseVFS(name string, raw []byte) (Snapshot, error) {
	var root map[string]any
	if len(raw) > 65536 || json.Unmarshal(raw, &root) != nil || root == nil {
		return Unknown(name, "invalid_vfs_response"), errors.New("invalid VFS response")
	}
	disk, ok := root["diskCache"].(map[string]any)
	if !ok {
		return Unknown(name, "disk_cache_unavailable"), nil
	}
	q, qok := counter(disk["uploadsQueued"])
	a, aok := counter(disk["uploadsInProgress"])
	e, eok := counter(disk["erroredFiles"])
	// inUse is a count of VFS references (often 1 when idle), NOT open files.
	use, useOK := counter(root["inUse"])
	if !useOK {
		return Unknown(name, "in_use_unavailable"), nil
	}
	if !qok || !aok || !eok {
		return Unknown(name, "upload_counters_unavailable"), nil
	}
	s := Snapshot{Mount: name, Queued: q, Active: a, Errors: e, InUse: use, Source: "authenticated_vfs_stats"}
	switch {
	case e > 0:
		s.State = "errored"
		s.Reason = "writeback_errors"
	case q > 0 || a > 0:
		s.State = "busy"
		s.Reason = "writeback_pending"
	default:
		s.State = "idle"
		s.Reason = "writeback_drained"
	}
	return s, nil
}
