// Package brokergrant contains R1's deny-by-default, testable grant policy.
// It intentionally does NOT expose the private daemon socket or mint grants for
// remote callers. Only a future authenticated broker control plane may Issue.
package brokergrant

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"strings"
	"sync"
	"time"
)

type Identity struct {
	UID uint32
	// ProcessKey must be derived from a trusted process verifier (package digest,
	// immutable executable identity, /proc start-time binding), NEVER from RPC.
	ProcessKey string
}
type GrantSpec struct {
	Caller     Identity
	Remote     string
	Prefix     string
	Operations []string
	TTL        time.Duration
}
type GrantReceipt struct {
	ID        string    `json:"id"`
	ExpiresAt time.Time `json:"expires_at"`
}
type ticket struct {
	GrantReceipt
	Caller         Identity
	Remote, Prefix string
	Operations     map[string]struct{}
}
type Store struct {
	mu     sync.RWMutex
	now    func() time.Time
	grants map[[32]byte]ticket
	index  map[string][32]byte
}

var readOps = map[string]bool{"system.capabilities": true, "rclone.version": true, "rclone.listremotes": true, "rclone.lsjson": true, "rclone.size": true}

func New() *Store {
	return &Store{now: time.Now, grants: make(map[[32]byte]ticket), index: make(map[string][32]byte)}
}

// NewWithClock supports deterministic expiry tests, not a runtime time source.
func NewWithClock(now func() time.Time) *Store { s := New(); s.now = now; return s }
func validRemote(r string) bool {
	if len(r) == 0 || len(r) > 128 {
		return false
	}
	for _, c := range r {
		if !(c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z' || c >= '0' && c <= '9' || c == '_' || c == '-' || c == '.') {
			return false
		}
	}
	return true
}
func cleanPrefix(p string) bool {
	if len(p) > 4096 || strings.HasPrefix(p, "/") || strings.ContainsAny(p, "\\%?#\x00") {
		return false
	}
	if p == "" {
		return true
	}
	for _, c := range p {
		if c < 32 || c == 127 {
			return false
		}
	}
	for _, component := range strings.Split(p, "/") {
		if component == "" || component == "." || component == ".." {
			return false
		}
	}
	return true
}
func within(prefix, path string) bool {
	if !cleanPrefix(path) {
		return false
	}
	return prefix == "" || path == prefix || strings.HasPrefix(path, prefix+"/")
}
func (s *Store) Issue(spec GrantSpec) (string, GrantReceipt, error) {
	if spec.Caller.ProcessKey == "" || !validRemote(spec.Remote) || !cleanPrefix(spec.Prefix) || spec.TTL <= 0 || spec.TTL > 24*time.Hour || len(spec.Operations) == 0 {
		return "", GrantReceipt{}, errors.New("invalid_grant_scope")
	}
	ops := make(map[string]struct{}, len(spec.Operations))
	for _, op := range spec.Operations {
		if !readOps[op] {
			return "", GrantReceipt{}, errors.New("write_or_unknown_operation_denied")
		}
		ops[op] = struct{}{}
	}
	raw := make([]byte, 32)
	if _, err := rand.Read(raw); err != nil {
		return "", GrantReceipt{}, err
	}
	token := hex.EncodeToString(raw)
	key := sha256.Sum256([]byte(token))
	idBytes := make([]byte, 16)
	if _, err := rand.Read(idBytes); err != nil {
		return "", GrantReceipt{}, err
	}
	receipt := GrantReceipt{ID: hex.EncodeToString(idBytes), ExpiresAt: s.now().Add(spec.TTL)}
	entry := ticket{GrantReceipt: receipt, Caller: spec.Caller, Remote: spec.Remote, Prefix: spec.Prefix, Operations: ops}
	s.mu.Lock()
	defer s.mu.Unlock()
	s.grants[key] = entry
	s.index[receipt.ID] = key
	return token, receipt, nil
}

// Authorize verifies caller identity from the transport, exact token, time,
// class-restricted operation, remote and segment-bound path. The caller MUST
// separately extract the true target path from the parsed typed RPC command.
func (s *Store) Authorize(token string, peer Identity, op, remote, path string) error {
	if len(token) != 64 || peer.ProcessKey == "" || !readOps[op] || !validRemote(remote) || !cleanPrefix(path) {
		return errors.New("not_authorized")
	}
	key := sha256.Sum256([]byte(token))
	s.mu.RLock()
	entry, ok := s.grants[key]
	s.mu.RUnlock()
	if !ok || entry.Caller != peer || !s.now().Before(entry.ExpiresAt) || entry.Remote != remote || !within(entry.Prefix, path) {
		return errors.New("not_authorized")
	}
	if _, ok = entry.Operations[op]; !ok {
		return errors.New("not_authorized")
	}
	return nil
}
func (s *Store) Revoke(id string) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	key, ok := s.index[id]
	if !ok {
		return false
	}
	delete(s.grants, key)
	delete(s.index, id)
	return true
}
