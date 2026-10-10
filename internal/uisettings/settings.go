// Package uisettings owns Skybind's private, revisioned browser preferences.
// These preferences are never runtime, mount, or privileged authority.
package uisettings

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"skybind/internal/atomicfile"
	"skybind/internal/previewproof"
	"skybind/internal/protocol"
	"sync"
	"time"
)

const fileName = "settings-v1.json"

type Settings struct {
	RefreshSeconds   int    `json:"refresh_seconds"`
	LogLimit         int    `json:"log_limit"`
	LogMaxBytes      int    `json:"log_max_bytes"`
	LogBackups       int    `json:"log_backups"`
	WebUIIdleSeconds int    `json:"webui_idle_seconds"`
	DefaultView      string `json:"default_view"`
	DefaultMountView string `json:"default_mount_view"`
	LogFollow        bool   `json:"log_follow"`
	DenseMode        bool   `json:"dense_mode"`
	ReducedMotion    bool   `json:"reduced_motion"`
}
type Snapshot struct {
	Revision uint64   `json:"revision"`
	Settings Settings `json:"settings"`
}
type Preview struct {
	CurrentRevision uint64   `json:"current_revision"`
	Settings        Settings `json:"settings"`
	CandidateDigest string   `json:"candidate_digest"`
	PreviewProof    string   `json:"preview_proof"`
}
type Store struct {
	mu       sync.Mutex
	dir      string
	snapshot Snapshot
	proofs   *previewproof.Store
}

func Defaults() Settings {
	return Settings{RefreshSeconds: 5, LogLimit: 100, LogMaxBytes: 1048576, LogBackups: 3, WebUIIdleSeconds: 900, DefaultView: "home", DefaultMountView: "cards", LogFollow: true}
}
func Valid(s Settings) error {
	if s.RefreshSeconds < 2 || s.RefreshSeconds > 60 || s.LogLimit < 20 || s.LogLimit > 500 || s.LogMaxBytes < 16384 || s.LogMaxBytes > 67108864 || s.LogBackups < 1 || s.LogBackups > 12 || s.WebUIIdleSeconds < 30 || s.WebUIIdleSeconds > 3600 {
		return errors.New("settings policy out of bounds")
	}
	views := map[string]bool{"home": true, "mounts": true, "jobs": true, "activity": true, "more": true, "runtime": true, "remotes": true, "doctor": true, "logs": true, "settings": true}
	if !views[s.DefaultView] || (s.DefaultMountView != "cards" && s.DefaultMountView != "dense") {
		return errors.New("invalid UI view selection")
	}
	return nil
}
func Open(dir string) (*Store, error) {
	s := &Store{dir: dir, snapshot: Snapshot{Revision: 0, Settings: Defaults()}, proofs: previewproof.New()}
	b, e := atomicfile.Read(dir, fileName, 4096)
	if errors.Is(e, os.ErrNotExist) {
		return s, nil
	}
	if e != nil {
		return nil, e
	}
	if e = protocol.StrictBytes(b, &s.snapshot); e != nil {
		return nil, e
	}
	if e = Valid(s.snapshot.Settings); e != nil {
		return nil, e
	}
	return s, nil
}
func (s *Store) Snapshot() Snapshot { s.mu.Lock(); defer s.mu.Unlock(); return s.snapshot }
func (s *Store) Preview(candidate Settings) (Preview, error) {
	if e := Valid(candidate); e != nil {
		return Preview{}, e
	}
	b, _ := json.Marshal(candidate)
	s.mu.Lock()
	defer s.mu.Unlock()
	digest := previewproof.Digest(b)
	token, e := s.proofs.Issue(previewproof.Binding{Action: "ui.settings.apply", Subject: "skybind-ui", Revision: s.snapshot.Revision, Digest: digest}, 90*time.Second)
	if e != nil {
		return Preview{}, e
	}
	return Preview{CurrentRevision: s.snapshot.Revision, Settings: candidate, CandidateDigest: digest, PreviewProof: token}, nil
}
func (s *Store) Apply(revision uint64, settings Settings, digest, token string) (Snapshot, error) {
	if e := Valid(settings); e != nil {
		return Snapshot{}, e
	}
	b, _ := json.Marshal(settings)
	if digest != previewproof.Digest(b) {
		return Snapshot{}, errors.New("settings proof digest mismatch")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if revision != s.snapshot.Revision {
		return Snapshot{}, errors.New("stale settings revision")
	}
	if e := s.proofs.Consume(token, previewproof.Binding{Action: "ui.settings.apply", Subject: "skybind-ui", Revision: revision, Digest: digest}); e != nil {
		return Snapshot{}, e
	}
	next := Snapshot{Revision: revision + 1, Settings: settings}
	data, e := json.Marshal(next)
	if e != nil {
		return Snapshot{}, e
	}
	if e = atomicfile.Write(s.dir, fileName, append(data, '\n')); e != nil {
		return Snapshot{}, fmt.Errorf("settings atomic publication: %w", e)
	}
	s.snapshot = next
	return next, nil
}
