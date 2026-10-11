// Package platformlifecycle retains persistent user state across uninstall.
package platformlifecycle

import (
	"errors"
	"os"
	"skybind/internal/mounts/lifecycle"
	"skybind/internal/namespace"
)

// Owned mounts are stopped only when no namespace bind ledger remains active.
// No blanket process kill, unmount, or root-state removal is permitted.
func StopOwned(mount *lifecycle.Engine, ns *namespace.Manager) ([]string, error) {
	if os.Geteuid() != 0 {
		return nil, errors.New("root required")
	}
	names, e := mount.List()
	if e != nil {
		return nil, e
	}
	stopped := []string{}
	for _, name := range names {
		if ns != nil {
			safe, e := ns.NoOutstanding(name)
			if e != nil || !safe {
				return stopped, errors.New("namespace ownership must be separately released before stopping FUSE")
			}
		}
		if _, e = mount.Stop(name); e != nil {
			return stopped, e
		}
		stopped = append(stopped, name)
	}
	return stopped, nil
}
