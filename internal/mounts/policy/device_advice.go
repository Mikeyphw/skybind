package policy

import (
	"os"
	"strconv"
	"strings"
	"syscall"
)

// DeviceAdvice uses read-only kernel resource facts, never a GUI-supplied RAM
// or free-storage value. It does not persist or activate any profile.
func DeviceAdvice(cachePath string) Advice {
	raw, err := os.ReadFile("/proc/meminfo")
	if err != nil || len(raw) > 1<<20 {
		return Advice{Reason: "memory_unknown"}
	}
	var ram int64
	for _, line := range strings.Split(string(raw), "\n") {
		fields := strings.Fields(line)
		if len(fields) == 3 && fields[0] == "MemTotal:" && fields[2] == "kB" {
			v, e := strconv.ParseInt(fields[1], 10, 64)
			if e == nil && v > 0 && v <= (1<<52)/1024 {
				ram = v * 1024
			}
			break
		}
	}
	var stat syscall.Statfs_t
	if ram == 0 || syscall.Statfs(cachePath, &stat) != nil || stat.Bsize <= 0 {
		return Advice{Reason: "resource_facts_unavailable"}
	}
	free := int64(stat.Bavail) * int64(stat.Bsize)
	if free < 0 {
		return Advice{Reason: "storage_unavailable"}
	}
	return Recommend(ram, free)
}
