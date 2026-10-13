package rc

// Performance summarizes authenticated per-mount RC counters without emitting
// filenames, paths, transfer objects, remote configuration, or credentials.
// Speed is rclone core/stats aggregate throughput: direction is NOT known.
import (
	"math"
	"time"
)

type Performance struct {
	State                    string   `json:"state"` // available, partial, unavailable
	SampledAtUnixMS          int64    `json:"sampled_at_unix_ms"`
	TotalSpeedBytesPerSecond *float64 `json:"total_speed_bytes_per_second"`
	TransferredBytes         *float64 `json:"transferred_bytes"`
	RCErrors                 *float64 `json:"rc_errors"`
	VFSCacheBytes            *float64 `json:"vfs_cache_bytes"`
	VFSCacheFiles            *float64 `json:"vfs_cache_files"`
	Source                   string   `json:"source"`
}

func finiteCounter(source map[string]any, key string) *float64 {
	if source == nil {
		return nil
	}
	v, ok := source[key].(float64)
	if !ok || math.IsNaN(v) || math.IsInf(v, 0) || v < 0 || v > 1e15 {
		return nil
	}
	// Reject fractional counts for byte and count metrics; speeds may be fractional.
	if key != "speed" && math.Trunc(v) != v {
		return nil
	}
	return &v
}

func summarizePerformance(core, vfs map[string]any) Performance {
	p := Performance{State: "unavailable", SampledAtUnixMS: time.Now().UnixMilli(), Source: "authenticated_rclone_rc_aggregate"}
	p.TotalSpeedBytesPerSecond = finiteCounter(core, "speed")
	p.TransferredBytes = finiteCounter(core, "bytes")
	p.RCErrors = finiteCounter(core, "errors")
	if cache, ok := vfs["diskCache"].(map[string]any); ok {
		p.VFSCacheBytes = finiteCounter(cache, "bytesUsed")
		p.VFSCacheFiles = finiteCounter(cache, "files")
	}
	populated := 0
	for _, v := range []*float64{p.TotalSpeedBytesPerSecond, p.TransferredBytes, p.RCErrors, p.VFSCacheBytes, p.VFSCacheFiles} {
		if v != nil {
			populated++
		}
	}
	if populated == 5 {
		p.State = "available"
	} else if populated > 0 {
		p.State = "partial"
	}
	return p
}
