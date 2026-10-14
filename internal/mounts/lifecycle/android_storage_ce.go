package lifecycle

import (
	"context"
	"os"
	"os/exec"
	"strings"
	"time"
)

// androidUserStorageLocked applies ONLY to emulated storage for Android user 0.
// A property read that fails, times out or returns an unknown value never
// overrides normal source validation or mount-start retry limits.
func androidUserStorageLocked(mountpoint string) bool {
	if !strings.HasPrefix(mountpoint, "/storage/emulated/0/") {
		return false
	}
	if _, err := os.Stat("/system/bin/getprop"); err != nil {
		return false
	}
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, "/system/bin/getprop", "sys.user.0.ce_available")
	cmd.Env = []string{"PATH=/system/bin:/system/xbin"}
	out, err := cmd.Output()
	if err != nil || len(out) > 16 || ctx.Err() != nil {
		return false
	}
	return userStorageLockedForProperty(mountpoint, strings.TrimSpace(string(out)))
}

func userStorageLockedForProperty(mountpoint, value string) bool {
	if !strings.HasPrefix(mountpoint, "/storage/emulated/0/") {
		return false
	}
	return value == "false" || value == "0"
}
