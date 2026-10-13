package rc

import (
	"encoding/json"
	"math"
	"strings"
	"testing"
)

func TestM02PerformanceSanitizedAndMissingNotZero(t *testing.T) {
	core := map[string]any{"speed": float64(125.25), "bytes": float64(2048), "errors": float64(0), "transferring": []any{map[string]any{"name": "secret_file.txt"}}}
	vfs := map[string]any{"diskCache": map[string]any{"bytesUsed": float64(4000), "files": float64(4), "path": "/my/private/cache"}}
	p := summarizePerformance(core, vfs)
	if p.State != "available" || p.TotalSpeedBytesPerSecond == nil || *p.TotalSpeedBytesPerSecond != 125.25 || p.VFSCacheFiles == nil {
		t.Fatalf("unexpected performance %+v", p)
	}
	b, _ := json.Marshal(p)
	if strings.Contains(string(b), "secret") || strings.Contains(string(b), "/my/private") {
		t.Fatal("leaked raw RC fields")
	}
	empty := summarizePerformance(map[string]any{}, map[string]any{})
	if empty.State != "unavailable" || empty.TotalSpeedBytesPerSecond != nil || empty.VFSCacheBytes != nil {
		t.Fatalf("missing data turned into a number: %+v", empty)
	}
	partial := summarizePerformance(map[string]any{"speed": float64(1)}, nil)
	if partial.State != "partial" || partial.VFSCacheBytes != nil {
		t.Fatalf("partial data not preserved: %+v", partial)
	}
}
func TestM02PerformanceRejectsInvalidNumbers(t *testing.T) {
	for _, invalid := range []any{-1.0, math.NaN(), math.Inf(1), "8", true, 2e16, 3.3} {
		if finiteCounter(map[string]any{"bytes": invalid}, "bytes") != nil {
			t.Fatalf("accepted invalid byte count %v", invalid)
		}
	}
	if finiteCounter(map[string]any{"speed": float64(1.25)}, "speed") == nil {
		t.Fatal("rejected fractional speed")
	}
}
