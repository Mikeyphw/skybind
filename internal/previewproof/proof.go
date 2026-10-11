// Package previewproof provides short-lived, single-spend mutation proofs.
package previewproof

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"sync"
	"time"
)

type Binding struct {
	Action   string
	Subject  string
	Revision uint64
	Digest   string
}
type record struct {
	binding  Binding
	deadline time.Time
}
type Store struct {
	mu    sync.Mutex
	proof map[string]record
	now   func() time.Time
}

func New() *Store { return &Store{proof: map[string]record{}, now: time.Now} }
func (s *Store) Issue(b Binding, ttl time.Duration) (string, error) {
	if ttl <= 0 || ttl > 5*time.Minute || b.Action == "" || b.Subject == "" || b.Digest == "" {
		return "", errors.New("invalid proof binding")
	}
	key := make([]byte, 32)
	if _, err := rand.Read(key); err != nil {
		return "", err
	}
	tok := hex.EncodeToString(key)
	s.mu.Lock()
	s.proof[tok] = record{b, s.now().Add(ttl)}
	s.mu.Unlock()
	return tok, nil
}
func (s *Store) Consume(token string, b Binding) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if len(token) != 64 {
		return errors.New("invalid proof")
	}
	r, ok := s.proof[token]
	if !ok {
		return errors.New("unknown or spent proof")
	}
	delete(s.proof, token)
	if !s.now().Before(r.deadline) || r.binding != b {
		return errors.New("expired or mismatched proof")
	}
	return nil
}
func Digest(b []byte) string { sum := sha256.Sum256(b); return hex.EncodeToString(sum[:]) }
