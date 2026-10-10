package daemon

import (
	"os"
	"path/filepath"
	"skybind/internal/mounts/cache"
	"skybind/internal/mounts/config"
	"skybind/internal/mounts/lifecycle"
	"skybind/internal/mounts/policy"
	"skybind/internal/mounts/supervisor"
	"testing"
)

func TestCanonicalMountOperationRegistration(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "config")
	if err := os.Mkdir(dir, 0700); err != nil {
		t.Fatal(err)
	}
	store, err := config.Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	m := lifecycle.Canonical(store)
	e := EngineWithMounts(nil, store, m, cache.Canonical(nil), supervisor.New(m), func() policy.Facts { return policy.Facts{Network: policy.Unknown} })
	all := map[string]bool{}
	for _, v := range e.Descriptors() {
		all[v.Operation] = true
	}
	for _, name := range []string{"mount.list", "mount.status", "mount.health", "mount.start.preview", "mount.start", "mount.stop", "mount.restart", "mount.reconcile", "policy.status", "vfs.profiles", "cache.status", "cache.prune.preview", "cache.prune", "cache.clear.preview", "cache.clear", "cache.forget.preview", "cache.forget"} {
		if !all[name] {
			t.Fatalf("not registered: %s", name)
		}
	}
}
