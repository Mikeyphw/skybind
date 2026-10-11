// Package config owns Skybind's revisioned mount registry and guarded publication.
package config

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"skybind/internal/atomicfile"
	"skybind/internal/previewproof"
	"skybind/internal/protocol"
	"sort"
	"strings"
	"sync"
	"time"
)

const RegistryName = "registry-v2.json"
const PreviousName = "previous-v2.json"
const PendingName = "pending-v2.json"

var safeName = regexp.MustCompile(`^[a-zA-Z][a-zA-Z0-9_-]{0,62}$`)
var safeRemote = regexp.MustCompile(`^[a-zA-Z0-9_.-]+:(?:[^\x00\r\n]*)$`)

// Mount consists only of public, typed fields. Root-local args files are not
// supplied or serialized by clients. Unknown fields are rejected throughout.
type Mount struct {
	Name                 string `json:"name"`
	Enabled              bool   `json:"enabled"`
	Remote               string `json:"remote"`
	Mountpoint           string `json:"mountpoint"`
	VFSProfile           string `json:"vfs_profile"`
	CacheMode            string `json:"cache_mode"`
	CacheMaxBytes        int64  `json:"cache_max_bytes"`
	CacheMaxAgeSeconds   int64  `json:"cache_max_age_seconds"`
	DirCacheSeconds      int64  `json:"dir_cache_seconds"`
	PollSeconds          int64  `json:"poll_seconds"`
	AllowOther           bool   `json:"allow_other"`
	ReadOnly             bool   `json:"read_only"`
	LogLevel             string `json:"log_level"`
	NetworkMode          string `json:"network_mode"`
	ChargingOnly         bool   `json:"charging_only"`
	MinBatteryPercent    int    `json:"min_battery_percent"`
	MinCacheFreeBytes    int64  `json:"min_cache_free_bytes"`
	BootSettleSeconds    int    `json:"boot_settle_seconds"`
	NetworkSettleSeconds int    `json:"network_settle_seconds"`
	CacheHighPercent     int    `json:"cache_high_percent"`
	CacheLowPercent      int    `json:"cache_low_percent"`
}
type Registry struct {
	SchemaVersion int     `json:"schema_version"`
	Revision      uint64  `json:"revision"`
	Mounts        []Mount `json:"mounts"`
}
type Effect struct {
	Name      string `json:"name"`
	Change    string `json:"change"`
	Restart   bool   `json:"restart"`
	Cache     string `json:"cache"`
	Namespace string `json:"namespace"`
}
type Plan struct {
	BaseRevision    uint64   `json:"base_revision"`
	CandidateDigest string   `json:"candidate_digest"`
	Effects         []Effect `json:"effects"`
	Token           string   `json:"proof,omitempty"`
}

func Empty() Registry { return Registry{SchemaVersion: 2, Revision: 0, Mounts: []Mount{}} }
func normalize(r Registry) (Registry, error) {
	if r.SchemaVersion != 2 {
		return r, errors.New("unsupported registry schema")
	}
	if len(r.Mounts) > 128 {
		return r, errors.New("too many mounts")
	}
	seen := map[string]bool{}
	destinations := []string{}
	for i := range r.Mounts {
		m := &r.Mounts[i]
		if !safeName.MatchString(m.Name) || seen[m.Name] {
			return r, errors.New("invalid/duplicate mount name")
		}
		seen[m.Name] = true
		if !safeRemote.MatchString(m.Remote) || strings.ContainsAny(m.Remote, "\\\x00\r\n") || len(m.Remote) > 1024 {
			return r, errors.New("invalid remote")
		}
		if !filepath.IsAbs(m.Mountpoint) || filepath.Clean(m.Mountpoint) != m.Mountpoint || strings.ContainsAny(m.Mountpoint, "\\\x00\r\n") {
			return r, errors.New("invalid mountpoint")
		}
		if !(strings.HasPrefix(m.Mountpoint, "/storage/") || strings.HasPrefix(m.Mountpoint, "/mnt/")) {
			return r, errors.New("mountpoint outside supported storage")
		}
		if len(m.Mountpoint) > 256 {
			return r, errors.New("mountpoint too long")
		}
		for _, other := range destinations {
			if m.Mountpoint == other || strings.HasPrefix(m.Mountpoint, other+"/") || strings.HasPrefix(other, m.Mountpoint+"/") {
				return r, errors.New("overlapping mountpoints")
			}
		}
		destinations = append(destinations, m.Mountpoint)
		if !oneOf(m.VFSProfile, "", "streaming", "balanced", "offline", "minimal", "custom") || !oneOf(m.CacheMode, "", "off", "minimal", "writes", "full") || !oneOf(m.NetworkMode, "", "any", "wifi", "unmetered", "offline-allowed") || !oneOf(m.LogLevel, "", "DEBUG", "INFO", "NOTICE", "ERROR") {
			return r, errors.New("invalid policy enumeration")
		}
		if m.CacheMaxBytes < 0 || m.CacheMaxBytes > 1<<44 || m.MinCacheFreeBytes < 0 || m.MinCacheFreeBytes > 1<<44 || m.CacheMaxAgeSeconds < 0 || m.CacheMaxAgeSeconds > 31536000 || m.DirCacheSeconds < 0 || m.DirCacheSeconds > 31536000 || m.PollSeconds < 0 || m.PollSeconds > 86400 {
			return r, errors.New("invalid cache or polling limit")
		}
		if m.MinBatteryPercent < 0 || m.MinBatteryPercent > 100 || m.BootSettleSeconds < 0 || m.BootSettleSeconds > 3600 || m.NetworkSettleSeconds < 0 || m.NetworkSettleSeconds > 3600 || m.CacheLowPercent < 0 || m.CacheHighPercent < 0 || m.CacheHighPercent > 100 || m.CacheLowPercent > m.CacheHighPercent {
			return r, errors.New("invalid resource threshold")
		}
	}
	// Canonical sorting prevents semantically identical reorderings from defeating proofs.
	sort.Slice(r.Mounts, func(i, j int) bool { return r.Mounts[i].Name < r.Mounts[j].Name })
	return r, nil
}
func oneOf(v string, allowed ...string) bool {
	for _, x := range allowed {
		if v == x {
			return true
		}
	}
	return false
}
func Validate(data []byte) (Registry, error) {
	var r Registry
	if len(data) > 1<<20 {
		return r, errors.New("config too large")
	}
	if e := protocol.StrictBytes(data, &r); e != nil {
		return r, e
	}
	return normalize(r)
}
func digest(r Registry) string {
	r.Revision = 0
	b, _ := json.Marshal(r)
	d := sha256.Sum256(b)
	return hex.EncodeToString(d[:])
}
func Diff(before, after Registry) []Effect {
	old := map[string]Mount{}
	now := map[string]Mount{}
	for _, m := range before.Mounts {
		old[m.Name] = m
	}
	for _, m := range after.Mounts {
		now[m.Name] = m
	}
	effects := []Effect{}
	for name, a := range now {
		b, ok := old[name]
		if !ok {
			effects = append(effects, Effect{name, "create", a.Enabled, "new_cache", "new_visibility"})
			continue
		}
		if a == b {
			continue
		}
		restart := a.Remote != b.Remote || a.Mountpoint != b.Mountpoint || a.AllowOther != b.AllowOther || a.ReadOnly != b.ReadOnly || a.CacheMode != b.CacheMode || a.CacheMaxBytes != b.CacheMaxBytes || a.CacheMaxAgeSeconds != b.CacheMaxAgeSeconds || a.DirCacheSeconds != b.DirCacheSeconds || a.PollSeconds != b.PollSeconds || a.Enabled != b.Enabled
		cache := "unchanged"
		if a.CacheMaxBytes != b.CacheMaxBytes || a.CacheMode != b.CacheMode {
			cache = "policy_changed"
		}
		ns := "unchanged"
		if a.Mountpoint != b.Mountpoint || a.Enabled != b.Enabled {
			ns = "reinspect"
		}
		effects = append(effects, Effect{name, "update", restart, cache, ns})
	}
	for name := range old {
		if _, ok := now[name]; !ok {
			effects = append(effects, Effect{name, "delete", true, "retain_owned_only", "release_owned_only"})
		}
	}
	sort.Slice(effects, func(i, j int) bool { return effects[i].Name < effects[j].Name })
	return effects
}

type Store struct {
	mu     sync.Mutex
	dir    string
	proofs *previewproof.Store
}

func Open(dir string) (*Store, error) {
	s := &Store{dir: dir, proofs: previewproof.New()}
	if _, e := os.ReadDir(dir); e != nil {
		return nil, e
	}
	if e := s.recover(); e != nil {
		return nil, e
	}
	return s, nil
}
func (s *Store) read(name string) (Registry, error) {
	b, e := atomicfile.Read(s.dir, name, 1<<20)
	if os.IsNotExist(e) {
		return Empty(), nil
	}
	if e != nil {
		return Registry{}, e
	}
	return Validate(b)
}
func (s *Store) Snapshot() (Registry, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.read(RegistryName)
}
func (s *Store) Previous() (Registry, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.read(PreviousName)
}
func (s *Store) Preview(raw []byte) (Plan, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	cur, e := s.read(RegistryName)
	if e != nil {
		return Plan{}, e
	}
	candidate, e := Validate(raw)
	if e != nil {
		return Plan{}, e
	}
	if candidate.Revision != cur.Revision {
		return Plan{}, errors.New("stale config revision")
	}
	d := digest(candidate)
	bind := previewproof.Binding{Action: "config.apply", Subject: "registry", Revision: cur.Revision, Digest: d}
	token, e := s.proofs.Issue(bind, 2*time.Minute)
	if e != nil {
		return Plan{}, e
	}
	return Plan{cur.Revision, d, Diff(cur, candidate), token}, nil
}

// PrepareFunc executes under the registry publication lock, after a durable
// pending-recovery record exists and before publishing the new registry.
// It must fail closed if old owned mounts cannot be safely quiesced.
type PrepareFunc func(before, candidate Registry) error

func (s *Store) Apply(raw []byte, token string) (Registry, error) {
	return s.ApplyWithPrepare(raw, token, nil)
}
func (s *Store) ApplyWithPrepare(raw []byte, token string, prepare PrepareFunc) (Registry, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.apply(raw, token, "config.apply", prepare)
}
func (s *Store) apply(raw []byte, token, action string, prepare PrepareFunc) (Registry, error) {
	cur, e := s.read(RegistryName)
	if e != nil {
		return Registry{}, e
	}
	candidate, e := Validate(raw)
	if e != nil {
		return Registry{}, e
	}
	if candidate.Revision != cur.Revision {
		return Registry{}, errors.New("stale config revision")
	}
	d := digest(candidate)
	if e = s.proofs.Consume(token, previewproof.Binding{Action: action, Subject: "registry", Revision: cur.Revision, Digest: d}); e != nil {
		return Registry{}, e
	}
	candidate.Revision = cur.Revision + 1
	oldPrev, e := s.read(PreviousName)
	if e != nil {
		return Registry{}, e
	}
	txn := struct {
		Before   Registry `json:"before"`
		Previous Registry `json:"previous"`
	}{cur, oldPrev}
	b, _ := json.Marshal(txn)
	if e = atomicfile.Write(s.dir, PendingName, b); e != nil {
		return Registry{}, e
	}
	if prepare != nil {
		if e = prepare(cur, candidate); e != nil {
			// No registry revision has been published. Preserve any desired
			// mount intent so the supervisor can recover safely.
			if cleanupErr := s.finishPending(); cleanupErr != nil {
				return Registry{}, fmt.Errorf("prepare failed: %v; pending recovery: %w", e, cleanupErr)
			}
			return Registry{}, fmt.Errorf("config lifecycle preparation blocked: %w", e)
		}
	}
	if e = s.write(PreviousName, cur); e != nil {
		return Registry{}, e
	}
	if e = s.write(RegistryName, candidate); e != nil {
		return Registry{}, e
	}
	if e = s.finishPending(); e != nil {
		return Registry{}, e
	}
	return candidate, nil
}
func (s *Store) write(name string, r Registry) error {
	b, e := json.Marshal(r)
	if e != nil {
		return e
	}
	return atomicfile.Write(s.dir, name, b)
}
func (s *Store) finishPending() error {
	if e := os.Remove(filepath.Join(s.dir, PendingName)); e != nil {
		return e
	}
	d, e := os.Open(s.dir)
	if e != nil {
		return e
	}
	defer d.Close()
	return d.Sync()
}
func (s *Store) recover() error {
	b, e := atomicfile.Read(s.dir, PendingName, 1<<20)
	if os.IsNotExist(e) {
		return nil
	}
	if e != nil {
		return e
	}
	var txn struct {
		Before   Registry `json:"before"`
		Previous Registry `json:"previous"`
	}
	if e = protocol.StrictBytes(b, &txn); e != nil {
		return e
	}
	if _, e = normalize(txn.Before); e != nil {
		return e
	}
	if _, e = normalize(txn.Previous); e != nil {
		return e
	}
	if e = s.write(RegistryName, txn.Before); e != nil {
		return e
	}
	if e = s.write(PreviousName, txn.Previous); e != nil {
		return e
	}
	return s.finishPending()
}
func (s *Store) RollbackPreview() (Plan, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	cur, e := s.read(RegistryName)
	if e != nil {
		return Plan{}, e
	}
	prev, e := s.read(PreviousName)
	if e != nil {
		return Plan{}, e
	}
	if cur.Revision == 0 || prev.Revision >= cur.Revision {
		return Plan{}, errors.New("no previous known-good revision")
	}
	prev.Revision = cur.Revision
	d := digest(prev)
	tok, e := s.proofs.Issue(previewproof.Binding{Action: "config.rollback", Subject: "registry", Revision: cur.Revision, Digest: d}, 2*time.Minute)
	if e != nil {
		return Plan{}, e
	}
	return Plan{cur.Revision, d, Diff(cur, prev), tok}, nil
}
func (s *Store) Rollback(token string) (Registry, error) {
	return s.RollbackWithPrepare(token, nil)
}
func (s *Store) RollbackWithPrepare(token string, prepare PrepareFunc) (Registry, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	cur, e := s.read(RegistryName)
	if e != nil {
		return Registry{}, e
	}
	prev, e := s.read(PreviousName)
	if e != nil {
		return Registry{}, e
	}
	if cur.Revision == 0 || prev.Revision >= cur.Revision {
		return Registry{}, errors.New("no rollback target")
	}
	prev.Revision = cur.Revision
	b, _ := json.Marshal(prev)
	return s.apply(b, token, "config.rollback", prepare)
}
func (s *Store) Validate(raw []byte) (Registry, error) { return Validate(raw) }
func CheckFileSafe(p string) error {
	st, e := os.Lstat(p)
	if e != nil {
		return e
	}
	if st.Mode()&os.ModeSymlink != 0 {
		return fmt.Errorf("symlink target forbidden")
	}
	return nil
}
