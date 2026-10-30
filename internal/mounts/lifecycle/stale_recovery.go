package lifecycle

// An explicit recovery for a *proven absent* mount whose private PID record
// refers to a different/dead process. Never signal a PID, unmount, or auto-start.
import (
	"bytes"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"time"

	"skybind/internal/atomicfile"
	"skybind/internal/paths"
	"skybind/internal/previewproof"
)

// staleBindingLocked must run under Engine.mu and must not change state.
func (e *Engine) staleBindingLocked(name string) (previewproof.Binding, []byte, error) {
	if err := e.loadDesired(); err != nil {
		return previewproof.Binding{}, nil, err
	}
	m, err := e.getMount(name)
	if err != nil {
		return previewproof.Binding{}, nil, err
	}
	raw, err := atomicfile.Read(e.dir, "process-"+name+".json", 4096)
	if err != nil {
		return previewproof.Binding{}, nil, err
	}
	var rec Ownership
	if err = json.Unmarshal(raw, &rec); err != nil {
		return previewproof.Binding{}, nil, errors.New("invalid ownership record")
	}
	if rec.Name != m.Name || rec.Mountpoint != m.Mountpoint || rec.Executable != paths.Engine || rec.PID <= 0 || rec.StartTicks == 0 || rec.MountID == "" {
		return previewproof.Binding{}, nil, errors.New("ownership record not canonical")
	}
	tick, exe, identityErr := e.obs.Identity(rec.PID)
	if identityErr == nil && tick == rec.StartTicks && exe == rec.Executable {
		return previewproof.Binding{}, nil, errors.New("recorded FUSE process still owns its identity")
	}
	// Permission denial/uncertainty is NOT proof of a dead process.
	if identityErr != nil && !errors.Is(identityErr, os.ErrNotExist) && !errors.Is(identityErr, syscall.ESRCH) {
		return previewproof.Binding{}, nil, errors.New("process identity unverified")
	}
	v, exists, err := e.obs.Mount(m.Mountpoint)
	if err != nil {
		return previewproof.Binding{}, nil, errors.New("daemon mount namespace unverified")
	}
	_ = v
	if exists {
		return previewproof.Binding{}, nil, errors.New("mountpoint still mounted in daemon namespace")
	}
	if e.dir == filepath.Join(paths.StateRoot, "desired") {
		if err = verifyNoMountInProcessNamespaces(m.Mountpoint); err != nil {
			return previewproof.Binding{}, nil, err
		}
	}
	reg, err := e.store.Snapshot()
	if err != nil {
		return previewproof.Binding{}, nil, err
	}
	cfgRaw, err := json.Marshal(m)
	if err != nil {
		return previewproof.Binding{}, nil, err
	}
	// The bound record/config/revision are revalidated before the single use.
	digest := previewproof.Digest(append(append([]byte(nil), raw...), cfgRaw...))
	return previewproof.Binding{Action: "mount.stale.recover", Subject: name, Revision: reg.Revision, Digest: digest}, raw, nil
}

func (e *Engine) StaleRecoveryPreview(name string) (map[string]any, error) {
	e.mu.Lock()
	defer e.mu.Unlock()
	binding, _, err := e.staleBindingLocked(name)
	if err != nil {
		return nil, err
	}
	proof, err := e.proofs.Issue(binding, 2*time.Minute)
	if err != nil {
		return nil, err
	}
	return map[string]any{"mount": name, "proof": proof, "registry_revision": binding.Revision, "action": "archive_stale_record_and_disable_desired_only", "expires_seconds": 120, "device_qualified": false}, nil
}

func (e *Engine) RecoverStaleRecord(name, proof string, operatorApprove bool) (map[string]any, error) {
	if !operatorApprove {
		return nil, errors.New("explicit operator approval required")
	}
	e.mu.Lock()
	defer e.mu.Unlock()
	binding, raw, err := e.staleBindingLocked(name)
	if err != nil {
		return nil, err
	}
	if err = e.proofs.Consume(proof, binding); err != nil {
		return nil, err
	}
	// Archive BEFORE altering desired state, with an unpredictable fresh filename.
	nonce := make([]byte, 16)
	if _, err = rand.Read(nonce); err != nil {
		return nil, err
	}
	archived := "stale-ownership-" + name + "-" + hex.EncodeToString(nonce) + ".json"
	if err = atomicfile.Write(e.dir, archived, raw); err != nil {
		return nil, err
	}
	// A desired=true mount would otherwise restart automatically via supervisor.
	e.state[name] = false
	if err = e.persistDesired(); err != nil {
		return nil, err
	}
	// Recheck live presence and the exact archived bytes before unlinking.
	// The Engine lock excludes concurrent Skybind operations on this name.
	_, before, err := e.staleBindingLocked(name)
	if err != nil {
		return nil, err
	}
	if !bytes.Equal(raw, before) {
		return nil, errors.New("ownership record changed during recovery")
	}
	current, err := atomicfile.Read(e.dir, "process-"+name+".json", 4096)
	if err != nil || !bytes.Equal(current, raw) {
		return nil, errors.New("ownership record changed before unlink")
	}
	// Removing a private historical record never touches the real mount or PID.
	if err = os.Remove(e.recordFile(name)); err != nil {
		return nil, err
	}
	return map[string]any{"mount": name, "record_archived": true, "desired": false, "recovered": true, "mount_started": false, "process_signalled": false, "unmounted": false}, nil
}

// Strict all-readable-namespace check. Unreadable live namespaces fail closed.
// It does not claim to atomically freeze unrelated Android processes.
func verifyNoMountInProcessNamespaces(point string) error {
	entries, err := os.ReadDir("/proc")
	if err != nil {
		return errors.New("process namespace inventory unavailable")
	}
	seen := make(map[string]bool)
	checked := 0
	for _, entry := range entries {
		if _, err := strconv.Atoi(entry.Name()); err != nil {
			continue
		}
		checked++
		if checked > 8192 {
			return errors.New("process namespace inventory exceeds safe bound")
		}
		base := filepath.Join("/proc", entry.Name())
		namespace, err := os.Readlink(filepath.Join(base, "ns/mnt"))
		if err != nil {
			if errors.Is(err, os.ErrNotExist) {
				if _, statErr := os.Stat(base); errors.Is(statErr, os.ErrNotExist) {
					continue
				}
			}
			return errors.New("process mount namespace unreadable")
		}
		if seen[namespace] {
			continue
		}
		f, err := os.Open(filepath.Join(base, "mountinfo"))
		if err != nil {
			if errors.Is(err, os.ErrNotExist) {
				if _, statErr := os.Stat(base); errors.Is(statErr, os.ErrNotExist) {
					continue
				}
			}
			return errors.New("process mount inventory unreadable")
		}
		data, readErr := io.ReadAll(io.LimitReader(f, 4*1024*1024+1))
		closeErr := f.Close()
		if readErr != nil || closeErr != nil || len(data) > 4*1024*1024 {
			return errors.New("process mount inventory incomplete")
		}
		for _, line := range strings.Split(strings.TrimSpace(string(data)), "\n") {
			if line == "" {
				return errors.New("process mount inventory empty")
			}
			parts := strings.SplitN(line, " - ", 2)
			if len(parts) != 2 {
				return errors.New("process mount inventory malformed")
			}
			fields := strings.Fields(parts[0])
			if len(fields) < 5 {
				return errors.New("process mount inventory malformed")
			}
			if decodeMountField(fields[4]) == point {
				return fmt.Errorf("mountpoint still present in another process mount namespace")
			}
		}
		seen[namespace] = true
	}
	return nil
}
