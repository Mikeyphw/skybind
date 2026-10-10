package platformlifecycle

import (
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"skybind/internal/atomicfile"
	"skybind/internal/mounts/lifecycle"
	"skybind/internal/namespace"
	"skybind/internal/paths"
	"syscall"
	"time"
)

const PurgePhrase = "PURGE_SKYBIND_PERSISTENT_DATA"

type purgeProof struct {
	Hash    string `json:"hash"`
	Expires int64  `json:"expires"`
}

func privateRun() string { return filepath.Join(paths.StateRoot, "run") }

// PreviewPurge produces an independent root-only, time-bounded destructive proof.
// Normal Android module removal never calls this function.
func PreviewPurge() (string, error) {
	if os.Geteuid() != 0 {
		return "", errors.New("root required")
	}
	if err := paths.EnsurePrivateState(); err != nil {
		return "", err
	}
	token := make([]byte, 32)
	if _, err := rand.Read(token); err != nil {
		return "", err
	}
	raw := hex.EncodeToString(token)
	sum := sha256.Sum256([]byte(raw))
	b, _ := json.Marshal(purgeProof{Hash: hex.EncodeToString(sum[:]), Expires: time.Now().Add(2 * time.Minute).Unix()})
	if err := atomicfile.Write(privateRun(), "purge-proof.json", b); err != nil {
		return "", err
	}
	return raw, nil
}

// Purge requires exact root paths, a stopped daemon, zero owned mounts and
// zero outstanding namespace intents. It never unmounts a foreign filesystem.
func Purge(m *lifecycle.Engine, ns *namespace.Manager, token, phrase string) error {
	if os.Geteuid() != 0 || phrase != PurgePhrase || len(token) != 64 {
		return errors.New("explicit root purge proof required")
	}
	if err := paths.EnsurePrivateState(); err != nil {
		return err
	}
	b, e := atomicfile.Read(privateRun(), "purge-proof.json", 2048)
	if e != nil {
		return e
	}
	var p purgeProof
	if json.Unmarshal(b, &p) != nil || p.Expires <= time.Now().Unix() {
		return errors.New("expired or invalid purge proof")
	}
	sum := sha256.Sum256([]byte(token))
	want, e := hex.DecodeString(p.Hash)
	if e != nil || len(want) != 32 || subtle.ConstantTimeCompare(want, sum[:]) != 1 {
		return errors.New("purge proof mismatch")
	}
	// Spend the proof before conducting destructive operations.
	if e = os.Remove(filepath.Join(privateRun(), "purge-proof.json")); e != nil {
		return e
	}
	lock, e := os.OpenFile(filepath.Join(privateRun(), "skybindd.sock.lock"), os.O_RDWR, 0600)
	if e == nil {
		defer lock.Close()
		if e = syscall.Flock(int(lock.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); e != nil {
			return errors.New("daemon still running")
		}
		defer syscall.Flock(int(lock.Fd()), syscall.LOCK_UN)
	} else if !os.IsNotExist(e) {
		return e
	}
	names, e := m.List()
	if e != nil {
		return e
	}
	for _, n := range names {
		safe, e := ns.NoOutstanding(n)
		if e != nil || !safe {
			return fmt.Errorf("namespace bind may exist for %s", n)
		}
		st, e := m.Status(n)
		if e != nil || st.Observed != "STOPPED" {
			return fmt.Errorf("mount %s not proven stopped", n)
		}
	}
	// RemoveAll cannot follow symlinks within the private tree. The root's
	// entire parent chain was checked by EnsurePrivateState above.
	return os.RemoveAll(paths.StateRoot)
}
