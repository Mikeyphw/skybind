package featuregateway

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"skybind/internal/atomicfile"
	"skybind/internal/paths"
	"syscall"
	"time"
)

const maxMutationRecord = 8192
const mutationTTL = 90 * time.Second

// MutationRecord is private root-owned state, never serialized to a client.
// Its Submitted state is reserved DURABLY before any daemon side effect.
// No path or API automatically retries a Submitted record.
type MutationRecord struct {
	ID          string `json:"id"`
	RequestID   string `json:"request_id"`
	NativeID    string `json:"native_id"`
	Operation   string `json:"operation"`
	Mount       string `json:"mount"`
	CallerUID   uint32 `json:"caller_uid"`
	ProcessKey  string `json:"process_key"`
	Issued      int64  `json:"issued"`
	Expires     int64  `json:"expires"`
	NativeProof string `json:"native_proof,omitempty"`
	Digest      string `json:"digest"`
	State       string `json:"state"`
}

type MutationStore struct{ dir string }

func OpenMutationStore() (*MutationStore, error) {
	if os.Geteuid() != 0 {
		return nil, errors.New("api04_mutation_store_root_only")
	}
	return openMutationStoreAt(CanonicalMutationState)
}
func openMutationStoreAt(dir string) (*MutationStore, error) {
	if !filepath.IsAbs(dir) || filepath.Clean(dir) != dir {
		return nil, errors.New("api04_mutation_store_path")
	}
	fd, err := paths.OpenVerifiedDirectory(dir)
	if err != nil {
		return nil, err
	}
	defer syscall.Close(fd)
	st := syscall.Stat_t{}
	if syscall.Fstat(fd, &st) != nil || st.Uid != uint32(os.Geteuid()) || st.Mode&0777 != 0700 {
		return nil, errors.New("api04_mutation_store_untrusted")
	}
	return &MutationStore{dir: dir}, nil
}
func (s *MutationStore) withLock(fn func() error) error {
	if s == nil {
		return errors.New("api04_mutation_store_missing")
	}
	fd, err := paths.OpenVerifiedDirectory(s.dir)
	if err != nil {
		return err
	}
	defer syscall.Close(fd)
	lf, e := syscall.Openat(fd, ".mutation.lock", syscall.O_CREAT|syscall.O_RDWR|syscall.O_CLOEXEC|syscall.O_NOFOLLOW, 0600)
	if e != nil {
		return e
	}
	defer syscall.Close(lf)
	st := syscall.Stat_t{}
	if syscall.Fstat(lf, &st) != nil || st.Mode&syscall.S_IFMT != syscall.S_IFREG || st.Mode&0777 != 0600 || st.Uid != uint32(os.Geteuid()) || st.Nlink != 1 {
		return errors.New("api04_mutation_lock_untrusted")
	}
	if err = syscall.Flock(lf, syscall.LOCK_EX); err != nil {
		return err
	}
	defer syscall.Flock(lf, syscall.LOCK_UN)
	return fn()
}
func validMutationID(id string) bool {
	if len(id) != 32 {
		return false
	}
	_, err := hex.DecodeString(id)
	return err == nil
}
func (s *MutationStore) read(id string) (MutationRecord, error) {
	if !validMutationID(id) {
		return MutationRecord{}, errors.New("api04_mutation_id_invalid")
	}
	raw, err := atomicfile.Read(s.dir, id+".json", maxMutationRecord)
	if err != nil {
		return MutationRecord{}, err
	}
	var r MutationRecord
	if json.Unmarshal(raw, &r) != nil || r.ID != id || r.RequestID == "" || r.NativeID == "" || !mutationAllow[r.Operation] || !mountName.MatchString(r.Mount) || r.Expires <= r.Issued || r.Digest == "" {
		return MutationRecord{}, errors.New("api04_mutation_record_invalid")
	}
	return r, nil
}
func (s *MutationStore) write(r MutationRecord) error {
	if !validMutationID(r.ID) {
		return errors.New("api04_mutation_id_invalid")
	}
	b, e := json.Marshal(r)
	if e != nil || len(b) > maxMutationRecord {
		return errors.New("api04_mutation_record_too_large")
	}
	return atomicfile.Write(s.dir, r.ID+".json", b)
}
func newMutationID() (string, error) {
	b := make([]byte, 16)
	if _, e := rand.Read(b); e != nil {
		return "", e
	}
	return hex.EncodeToString(b), nil
}
func mutationDigest(r MutationRecord) string {
	// No daemon proof is displayed to the operator or an unprivileged client.
	sum := sha256.Sum256([]byte(r.ID + "\x00" + r.RequestID + "\x00" + r.NativeID + "\x00" + r.Operation + "\x00" + r.Mount + "\x00" + r.ProcessKey + "\x00" + r.NativeProof))
	return hex.EncodeToString(sum[:])
}
func (s *MutationStore) add(r MutationRecord) error {
	return s.withLock(func() error {
		if entries, e := os.ReadDir(s.dir); e != nil || len(entries) >= 2048 {
			return errors.New("api04_mutation_store_full")
		}
		if _, err := s.read(r.ID); err == nil {
			return errors.New("api04_mutation_collision")
		} else if !os.IsNotExist(err) {
			return err
		}
		return s.write(r)
	})
}
func (s *MutationStore) get(id string) (MutationRecord, error) {
	var r MutationRecord
	err := s.withLock(func() error { var e error; r, e = s.read(id); return e })
	return r, err
}
func (s *MutationStore) reserve(id, processKey string, uid uint32) (MutationRecord, error) {
	var r MutationRecord
	err := s.withLock(func() error {
		var e error
		r, e = s.read(id)
		if e != nil {
			return e
		}
		if r.State != "approved" || time.Now().Unix() >= r.Expires || r.CallerUID != uid || r.ProcessKey != processKey {
			return errors.New("api04_mutation_not_approved")
		}
		r.State = "submitted"
		return s.write(r)
	})
	return r, err
}

// Approve is exclusively a root operator action, never exposed on either
// cross-UID socket. Exact preview digest protects against approval mistakes.
func (s *MutationStore) Approve(id, expectedDigest string) error {
	if os.Geteuid() != 0 {
		return errors.New("api04_mutation_root_approval_required")
	}
	return s.approve(id, expectedDigest)
}

// ApproveExact additionally requires the operator to name the precise mount
// and mutation, not just paste an opaque consumer-supplied digest.
func (s *MutationStore) ApproveExact(id, digest, operation, mount string) error {
	if os.Geteuid() != 0 {
		return errors.New("api04_mutation_root_approval_required")
	}
	return s.approveExact(id, digest, operation, mount)
}
func (s *MutationStore) approveExact(id, digest, operation, mount string) error {
	if !mutationAllow[operation] || !mountName.MatchString(mount) {
		return errors.New("api04_mutation_approval_denied")
	}
	return s.withLock(func() error {
		r, e := s.read(id)
		if e != nil {
			return e
		}
		if r.State != "previewed" || time.Now().Unix() >= r.Expires || r.Operation != operation || r.Mount != mount || r.Digest != digest || len(digest) != 64 {
			return errors.New("api04_mutation_approval_denied")
		}
		r.State = "approved"
		return s.write(r)
	})
}
func (s *MutationStore) approve(id, expectedDigest string) error {
	return s.withLock(func() error {
		r, e := s.read(id)
		if e != nil {
			return e
		}
		if r.State != "previewed" || time.Now().Unix() >= r.Expires || len(expectedDigest) != 64 || r.Digest != expectedDigest {
			return errors.New("api04_mutation_approval_denied")
		}
		r.State = "approved"
		return s.write(r)
	})
}
func (s *MutationStore) SetOutcome(id, state string) error {
	if state != "succeeded" && state != "failed" && state != "unknown" {
		return errors.New("api04_mutation_state_invalid")
	}
	return s.withLock(func() error {
		r, e := s.read(id)
		if e != nil {
			return e
		}
		if r.State != "submitted" {
			return errors.New("api04_mutation_transition_denied")
		}
		r.State = state
		return s.write(r)
	})
}

// Operator summary deliberately excludes daemon proof, paths, credentials,
// and arguments. Returned only from the separate root-only approval binary.
func (s *MutationStore) Summary(id string) (MutationRecord, error) {
	if os.Geteuid() != 0 {
		return MutationRecord{}, errors.New("api04_root_only")
	}
	return s.get(id)
}
