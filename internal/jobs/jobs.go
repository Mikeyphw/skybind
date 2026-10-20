// Package jobs owns the revisioned Skybind transfer schedule. Only copy, sync,
// and check are executable; no client-provided flags or local shell execution.
package jobs

import (
	"bufio"
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"skybind/internal/atomicfile"
	"skybind/internal/mounts/config"
	"skybind/internal/mounts/policy"
	"skybind/internal/opevents"
	"skybind/internal/paths"
	"skybind/internal/previewproof"
	"skybind/internal/protocol"
	"strings"
	"sync"
	"time"
)

var jobName = regexp.MustCompile(`^[A-Za-z][A-Za-z0-9_-]{0,62}$`)
var endpointRE = regexp.MustCompile(`^[A-Za-z][A-Za-z0-9_-]{0,62}:(?:[^:\\\r\n\x00]*)$`)

// validEndpoint accepts credential-free remote paths and bounded Android media
// paths. Local paths never resolve into the private Skybind state or system tree.
func validEndpoint(s string) bool {
	if s == "" || len(s) > 768 || strings.ContainsAny(s, "\\\x00\r\n\t") {
		return false
	}
	if strings.HasPrefix(s, "/") {
		return validLocalEndpoint(s)
	}
	if !endpointRE.MatchString(s) {
		return false
	}
	p := strings.SplitN(s, ":", 2)[1]
	if strings.HasPrefix(p, "/") || strings.Contains(p, "//") {
		return false
	}
	for _, seg := range strings.Split(p, "/") {
		if seg == "." || seg == ".." {
			return false
		}
	}
	return true
}
func validLocalEndpoint(s string) bool {
	if !filepath.IsAbs(s) || filepath.Clean(s) != s || strings.Contains(s, ":") || strings.ContainsAny(s, "\\\x00\r\n\t") {
		return false
	}
	// Deliberately restrict privileged local transfer endpoints to Android
	// media trees. A job must never read/write /data/adb, /proc, /sys, /etc,
	// or an arbitrary app's private data through a root-owned daemon.
	allowed := []string{"/storage/emulated/", "/storage/self/primary/", "/storage/", "/sdcard/", "/mnt/media_rw/", "/mnt/user/", "/data/media/"}
	for _, prefix := range allowed {
		if strings.HasPrefix(s, prefix) && len(s) > len(prefix) {
			for _, seg := range strings.Split(s[len(prefix):], "/") {
				if seg == "" || seg == "." || seg == ".." {
					return false
				}
			}
			return true
		}
	}
	return false
}

// Local symlink escape guard: validate existing leaf/ancestors before executing
// a privileged external rclone process. Android's /sdcard alias itself is
// allowed, but arbitrary symlinks beneath media directories are not.
func validateLocalExisting(s string) error {
	if !strings.HasPrefix(s, "/") {
		return nil
	}
	if !validLocalEndpoint(s) {
		return errors.New("unsafe local job path")
	}
	begin := "/"
	parts := strings.Split(strings.TrimPrefix(s, "/"), "/")
	for _, part := range parts {
		begin = filepath.Join(begin, part)
		info, err := os.Lstat(begin)
		if errors.Is(err, os.ErrNotExist) {
			break
		}
		if err != nil {
			return errors.New("local job path inspection failed")
		}
		if info.Mode()&os.ModeSymlink != 0 && begin != "/sdcard" && begin != "/storage/self/primary" {
			return errors.New("local job path traverses a symlink")
		}
	}
	return nil
}

type Job struct {
	Name              string `json:"name"`
	Kind              string `json:"kind"`
	Source            string `json:"source"`
	Destination       string `json:"destination"`
	Enabled           bool   `json:"enabled"`
	IntervalSeconds   int64  `json:"interval_seconds"`
	NetworkMode       string `json:"network_mode"`
	ChargingOnly      bool   `json:"charging_only"`
	MinBatteryPercent int    `json:"min_battery_percent"`
	NextUnix          int64  `json:"next_unix"`
	LastRunID         string `json:"last_run_id,omitempty"`
	IgnoreExisting    bool   `json:"-"` // transient mountless copy: never overwrite an existing object
}
type Registry struct {
	SchemaVersion int    `json:"schema_version"`
	Revision      uint64 `json:"revision"`
	Jobs          []Job  `json:"jobs"`
}
type Run struct {
	ID                  string   `json:"id"`
	Name                string   `json:"name"`
	State               string   `json:"state"`
	StartedUnix         int64    `json:"started_unix"`
	FinishedUnix        int64    `json:"finished_unix,omitempty"`
	Reason              string   `json:"reason,omitempty"`
	Bytes               int64    `json:"bytes,omitempty"`
	SpeedBytesPerSecond float64  `json:"speed_bytes_per_second,omitempty"`
	ETASeconds          int64    `json:"eta_seconds,omitempty"`
	TotalBytes          *int64   `json:"total_bytes,omitempty"`
	Percent             *float64 `json:"percent,omitempty"`
	FilesDone           *int64   `json:"files_done,omitempty"`
	FilesTotal          *int64   `json:"files_total,omitempty"`
	ChecksDone          *int64   `json:"checks_done,omitempty"`
	ChecksTotal         *int64   `json:"checks_total,omitempty"`
	Errors              *int64   `json:"errors,omitempty"`
	RetryError          *bool    `json:"retry_error,omitempty"`
	TransferRetries     *int64   `json:"transfer_retries,omitempty"`
}
type persisted struct {
	Registry Registry `json:"registry"`
	Runs     []Run    `json:"runs"`
}
type Executor interface {
	Execute(context.Context, Job) error
}
type execRunner struct{}

// ProgressRunner is implemented only by the internally chosen command executor.
// The progress callback never receives stdout or any remote/config credentials.
type ProgressRunner interface {
	ExecuteWithProgress(context.Context, Job, func(int64, float64, int64)) error
}

// DetailedProgress is derived from numeric rclone JSON stats only. The default
// rclone stats do NOT report a numeric count of per-transfer retries; nil means
// unknown, not zero. No file names, paths, error text or secrets are retained.
type DetailedProgress struct {
	Bytes           int64
	Speed           float64
	ETA             int64
	TotalBytes      *int64
	FilesDone       *int64
	FilesTotal      *int64
	ChecksDone      *int64
	ChecksTotal     *int64
	Errors          *int64
	RetryError      *bool
	TransferRetries *int64
}
type DetailedProgressRunner interface {
	ExecuteWithDetailedProgress(context.Context, Job, func(DetailedProgress)) error
}

func (r execRunner) Execute(ctx context.Context, j Job) error {
	return r.ExecuteWithDetailedProgress(ctx, j, nil)
}
func (r execRunner) ExecuteWithProgress(ctx context.Context, j Job, update func(int64, float64, int64)) error {
	return r.ExecuteWithDetailedProgress(ctx, j, func(p DetailedProgress) {
		if update != nil {
			update(p.Bytes, p.Speed, p.ETA)
		}
	})
}
func (execRunner) ExecuteWithDetailedProgress(ctx context.Context, j Job, update func(DetailedProgress)) error {
	if err := validateLocalExisting(j.Source); err != nil {
		return err
	}
	if err := validateLocalExisting(j.Destination); err != nil {
		return err
	}
	if j.Kind != "copy" && j.Kind != "check" && j.Kind != "sync" && j.Kind != "moveto" {
		return errors.New("unsupported job execution kind")
	}
	if j.Kind == "moveto" {
		if err := execMoveGuard(j); err != nil {
			return err
		}
	}
	args := []string{"--config", paths.RcloneConfig, j.Kind, j.Source, j.Destination, "--stats", "1s", "--stats-log-level", "NOTICE", "--use-json-log", "--log-level", "NOTICE"}
	if j.IgnoreExisting {
		args = append(args, "--ignore-existing")
	}
	c := exec.CommandContext(ctx, paths.Engine, args...)
	c.Env = []string{"PATH=/system/bin:/system/xbin", "HOME=/data/adb/skybind"}
	c.Stdin = nil
	c.Stdout = io.Discard
	pipe, e := c.StderrPipe()
	if e != nil {
		return errors.New("unable to observe job")
	}
	if e = c.Start(); e != nil {
		return errors.New("rclone job launch failed")
	}
	scanner := bufio.NewScanner(pipe)
	scanner.Buffer(make([]byte, 4096), 65536)
	for scanner.Scan() {
		if update != nil {
			if stats, ok := decodeDetailedStats(scanner.Bytes()); ok {
				update(stats)
			}
		}
	}
	scanErr := scanner.Err()
	if e = c.Wait(); e != nil {
		return errors.New("rclone job failed")
	}
	if scanErr != nil {
		return errors.New("rclone progress channel exceeded bound")
	}
	return nil
}
func decodeStats(line []byte) (int64, float64, int64, bool) {
	p, ok := decodeDetailedStats(line)
	return p.Bytes, p.Speed, p.ETA, ok
}

// decodeDetailedStats only reads allowlisted numeric/bool JSON fields. Standard
// rclone --use-json-log stats contain totalBytes, totalTransfers, transfers,
// errors and retryError. They do not contain per-transfer retry counts.
func decodeDetailedStats(line []byte) (DetailedProgress, bool) {
	var p DetailedProgress
	if len(line) > 65536 {
		return p, false
	}
	var root map[string]json.RawMessage
	if json.Unmarshal(line, &root) != nil {
		return p, false
	}
	stats := root
	if raw, present := root["stats"]; present {
		if json.Unmarshal(raw, &stats) != nil || stats == nil {
			return p, false
		}
	} else if root["bytes"] == nil && root["speed"] == nil {
		return p, false
	}
	intField := func(key string, max int64) (*int64, bool) {
		raw, present := stats[key]
		if !present || string(raw) == "null" {
			return nil, true
		}
		var n int64
		if json.Unmarshal(raw, &n) != nil || n < 0 || n > max {
			return nil, false
		}
		return &n, true
	}
	var ok bool
	var bytes *int64
	if bytes, ok = intField("bytes", 1<<60); !ok {
		return p, false
	}
	if bytes != nil {
		p.Bytes = *bytes
	}
	if raw := stats["speed"]; raw != nil && string(raw) != "null" {
		if json.Unmarshal(raw, &p.Speed) != nil || math.IsNaN(p.Speed) || math.IsInf(p.Speed, 0) || p.Speed < 0 || p.Speed > 1e15 {
			return DetailedProgress{}, false
		}
	}
	if eta, valid := intField("eta", 1<<40); !valid {
		return DetailedProgress{}, false
	} else if eta != nil {
		p.ETA = *eta
	}
	if p.TotalBytes, ok = intField("totalBytes", 1<<60); !ok {
		return DetailedProgress{}, false
	}
	if p.FilesDone, ok = intField("transfers", 1<<40); !ok {
		return DetailedProgress{}, false
	}
	if p.FilesTotal, ok = intField("totalTransfers", 1<<40); !ok {
		return DetailedProgress{}, false
	}
	if p.ChecksDone, ok = intField("checks", 1<<40); !ok {
		return DetailedProgress{}, false
	}
	if p.ChecksTotal, ok = intField("totalChecks", 1<<40); !ok {
		return DetailedProgress{}, false
	}
	if p.Errors, ok = intField("errors", 1<<40); !ok {
		return DetailedProgress{}, false
	}
	// This field is forward-compatible; stock rclone omits it. No estimate
	// is derived from errors or retryError because they have other meanings.
	if p.TransferRetries, ok = intField("transferRetries", 1<<40); !ok {
		return DetailedProgress{}, false
	}
	if raw, present := stats["retryError"]; present && string(raw) != "null" {
		var v bool
		if json.Unmarshal(raw, &v) != nil {
			return DetailedProgress{}, false
		}
		p.RetryError = &v
	}
	if bytes == nil && p.Speed == 0 && p.TotalBytes == nil && p.FilesDone == nil && p.FilesTotal == nil && p.ChecksDone == nil && p.ChecksTotal == nil && p.Errors == nil {
		return DetailedProgress{}, false
	}
	return p, true
}

type Store struct {
	mu            sync.Mutex
	dir           string
	state         persisted
	proofs        *previewproof.Store
	executor      Executor
	running       map[string]context.CancelFunc
	cancelling    map[string]bool
	eventObserver func(opevents.Event)
	interrupted   []Run
	lastEmitted   map[string]time.Time
	now           func() time.Time
	facts         func() policy.Facts
}

func Empty() Registry { return Registry{SchemaVersion: 1, Jobs: []Job{}} }
func validate(r Registry) (Registry, error) {
	if r.SchemaVersion != 1 || len(r.Jobs) > 128 {
		return r, errors.New("invalid job schema/count")
	}
	names := map[string]bool{}
	for _, j := range r.Jobs {
		if !jobName.MatchString(j.Name) || names[j.Name] {
			return r, errors.New("bad/duplicate job name")
		}
		names[j.Name] = true
		if j.Kind != "copy" && j.Kind != "sync" && j.Kind != "check" {
			return r, errors.New("invalid job kind")
		}
		if !validEndpoint(j.Source) || !validEndpoint(j.Destination) || j.Source == j.Destination ||
			(strings.HasPrefix(j.Source, "/") && strings.HasPrefix(j.Destination, "/") &&
				(strings.HasPrefix(j.Source, j.Destination+"/") || strings.HasPrefix(j.Destination, j.Source+"/"))) {
			return r, errors.New("unsafe job endpoints")
		}
		if j.IntervalSeconds != 0 && (j.IntervalSeconds < 300 || j.IntervalSeconds > 31536000) {
			return r, errors.New("unsupported schedule interval")
		}
		if j.NetworkMode != "" && j.NetworkMode != "any" && j.NetworkMode != "wifi" && j.NetworkMode != "unmetered" && j.NetworkMode != "offline-allowed" {
			return r, errors.New("invalid network mode")
		}
		if j.MinBatteryPercent < 0 || j.MinBatteryPercent > 100 || j.NextUnix < 0 {
			return r, errors.New("invalid job policy")
		}

	}
	return r, nil
}
func Open(dir string, executor Executor, facts func() policy.Facts) (*Store, error) {
	if executor == nil {
		return nil, errors.New("missing job executor")
	}
	s := &Store{dir: dir, proofs: previewproof.New(), executor: executor, running: map[string]context.CancelFunc{}, cancelling: map[string]bool{}, lastEmitted: map[string]time.Time{}, now: time.Now, facts: facts}
	b, e := atomicfile.Read(dir, "jobs-v1.json", 1<<19)
	if errors.Is(e, os.ErrNotExist) {
		s.state.persistDefault()
		return s, nil
	}
	if e != nil {
		return nil, e
	}
	if e = json.Unmarshal(b, &s.state); e != nil {
		return nil, e
	}
	if _, e = validatePersisted(s.state); e != nil {
		return nil, e
	}
	dirty := false
	for i := range s.state.Runs {
		if s.state.Runs[i].State == "RUNNING" {
			s.state.Runs[i].State = "INTERRUPTED"
			s.state.Runs[i].Reason = "daemon_restarted"
			s.state.Runs[i].FinishedUnix = s.now().Unix()
			s.interrupted = append(s.interrupted, s.state.Runs[i])
			dirty = true
		}
	}
	if dirty {
		if e = s.persist(); e != nil {
			return nil, e
		}
	}
	return s, nil
}
func (p *persisted) persistDefault() { p.Registry = Empty(); p.Runs = []Run{} }
func cloneState(p persisted) persisted {
	p.Registry = clone(p.Registry)
	p.Runs = append([]Run(nil), p.Runs...)
	return p
}
func validatePersisted(p persisted) (persisted, error) {
	if p.Registry.SchemaVersion != 1 || len(p.Registry.Jobs) > 128 || len(p.Runs) > 256 {
		return p, errors.New("invalid persisted job registry")
	}
	for _, j := range p.Registry.Jobs {
		j.LastRunID = ""
		if _, e := validate(Registry{SchemaVersion: 1, Jobs: []Job{j}}); e != nil {
			return p, e
		}
	}
	for _, r := range p.Runs {
		if len(r.ID) != 32 || !jobName.MatchString(r.Name) {
			return p, errors.New("invalid run record")
		}
		if r.Bytes < 0 || r.Bytes > 1<<60 || math.IsNaN(r.SpeedBytesPerSecond) || math.IsInf(r.SpeedBytesPerSecond, 0) ||
			r.SpeedBytesPerSecond < 0 || r.SpeedBytesPerSecond > 1e15 || r.ETASeconds < 0 || r.ETASeconds > 1<<40 {
			return p, errors.New("invalid run progress")
		}
		for _, n := range []*int64{r.TotalBytes, r.FilesDone, r.FilesTotal, r.ChecksDone, r.ChecksTotal, r.Errors, r.TransferRetries} {
			if n != nil && (*n < 0 || *n > 1<<60) {
				return p, errors.New("invalid run progress counter")
			}
		}
		if r.Percent != nil && (math.IsNaN(*r.Percent) || math.IsInf(*r.Percent, 0) || *r.Percent < 0 || *r.Percent > 100) {
			return p, errors.New("invalid run percentage")
		}
	}
	return p, nil
}
func Canonical() (*Store, error) {
	return Open(paths.StateRoot+"/jobs", execRunner{}, func() policy.Facts { return policy.SampleAndroidFacts(paths.StateRoot + "/cache") })
}
func (s *Store) persist() error {
	b, e := json.Marshal(s.state)
	if e != nil {
		return e
	}
	return atomicfile.Write(s.dir, "jobs-v1.json", b)
}
func (s *Store) Snapshot() (Registry, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	return clone(s.state.Registry), nil
}

// Clone into a non-nil slice: the public daemon contract requires [] rather
// than null for an empty registry. This also prevents callers from mutating
// the persisted registry's backing slice.
func clone(r Registry) Registry { r.Jobs = append([]Job{}, r.Jobs...); return r }

// RunStatus returns only a previously claimed job run; it cannot launch work.
// SetEventObserver wires the durable event publisher after opening the run
// registry. Previously in-flight runs are emitted as interrupted once on boot.
func (s *Store) SetEventObserver(fn func(opevents.Event)) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.eventObserver = fn
	for _, r := range s.interrupted {
		s.emit(r, "job.interrupted", "interrupted", "daemon_restarted")
	}
	s.interrupted = nil
}
func (s *Store) emit(r Run, kind, state, phase string) {
	if s.eventObserver == nil {
		return
	}
	event := opevents.Event{OperationID: r.ID, RunID: r.ID, Operation: "job.run", Type: kind, State: state, Phase: phase,
		Progress: &opevents.Progress{Bytes: r.Bytes, SpeedBytesPerSecond: r.SpeedBytesPerSecond, ETASeconds: r.ETASeconds,
			TotalBytes: r.TotalBytes, Percent: r.Percent, FilesDone: r.FilesDone, FilesTotal: r.FilesTotal, ChecksDone: r.ChecksDone, ChecksTotal: r.ChecksTotal,
			Errors: r.Errors, RetryError: r.RetryError, TransferRetries: r.TransferRetries}}
	s.eventObserver(event)
}
func (s *Store) RunStatus(id string) (Run, error) {
	if len(id) != 32 {
		return Run{}, errors.New("invalid run identity")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	for _, item := range s.state.Runs {
		if item.ID == id {
			return item, nil
		}
	}
	return Run{}, os.ErrNotExist
}

func (s *Store) Status() (any, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	// Keep the public jobs.status contract stable: an empty history is [], not null.
	return map[string]any{"registry": clone(s.state.Registry), "runs": append([]Run{}, s.state.Runs...)}, nil
}
func candidate(raw []byte) (Registry, error) {
	if len(raw) > 1<<18 {
		return Registry{}, errors.New("jobs candidate too large")
	}
	var r Registry
	e := protocol.StrictBytes(raw, &r)
	if e != nil {
		return r, e
	}
	return validate(r)
}

// Client submissions cannot fabricate next-run timestamps or run identities.
func (s *Store) checkManagedFields(r Registry) error {
	prior := map[string]Job{}
	for _, j := range s.state.Registry.Jobs {
		prior[j.Name] = j
	}
	for _, j := range r.Jobs {
		old, ok := prior[j.Name]
		if ok {
			if j.LastRunID != old.LastRunID || j.NextUnix != old.NextUnix {
				return errors.New("server-owned scheduling field changed")
			}
		}
		if !ok && (j.LastRunID != "" || j.NextUnix != 0) {
			return errors.New("new job contains server-owned fields")
		}
	}
	return nil
}
func (s *Store) Preview(raw []byte) (any, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	r, e := candidate(raw)
	if e != nil {
		return nil, e
	}
	if r.Revision != s.state.Registry.Revision {
		return nil, errors.New("stale jobs revision")
	}
	if e := s.checkManagedFields(r); e != nil {
		return nil, e
	}
	b, _ := json.Marshal(r)
	proof, e := s.proofs.Issue(previewproof.Binding{Action: "jobs.apply", Subject: "jobs", Revision: r.Revision, Digest: previewproof.Digest(b)}, 2*time.Minute)
	if e != nil {
		return nil, e
	}
	return map[string]any{"proof": proof, "base_revision": r.Revision, "job_count": len(r.Jobs), "includes_destructive_sync": hasSync(r.Jobs)}, nil
}
func hasSync(js []Job) bool {
	for _, j := range js {
		if j.Kind == "sync" {
			return true
		}
	}
	return false
}
func (s *Store) Apply(raw []byte, proof string) (Registry, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	r, e := candidate(raw)
	if e != nil {
		return Registry{}, e
	}
	if r.Revision != s.state.Registry.Revision {
		return Registry{}, errors.New("stale jobs revision")
	}
	if e := s.checkManagedFields(r); e != nil {
		return Registry{}, e
	}
	b, _ := json.Marshal(r)
	if e = s.proofs.Consume(proof, previewproof.Binding{Action: "jobs.apply", Subject: "jobs", Revision: r.Revision, Digest: previewproof.Digest(b)}); e != nil {
		return Registry{}, e
	}
	old := cloneState(s.state)
	r.Revision++
	for i := range r.Jobs {
		if r.Jobs[i].IntervalSeconds > 0 && r.Jobs[i].NextUnix == 0 {
			r.Jobs[i].NextUnix = s.now().Unix() + r.Jobs[i].IntervalSeconds
		}
	}
	s.state.Registry = r
	if e = s.persist(); e != nil {
		s.state = old
		return Registry{}, e
	}
	return clone(r), nil
}
func (s *Store) RunPreview(name string) (any, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	j, e := s.job(name)
	if e != nil {
		return nil, e
	}
	b, _ := json.Marshal(j)
	proof, e := s.proofs.Issue(previewproof.Binding{Action: "job.run", Subject: name, Revision: s.state.Registry.Revision, Digest: previewproof.Digest(b)}, 2*time.Minute)
	if e != nil {
		return nil, e
	}
	return map[string]any{"proof": proof, "name": name, "kind": j.Kind, "destructive": j.Kind == "sync", "source": j.Source, "destination": j.Destination}, nil
}
func (s *Store) job(name string) (Job, error) {
	for _, j := range s.state.Registry.Jobs {
		if j.Name == name {
			return j, nil
		}
	}
	return Job{}, errors.New("unknown job")
}
func (s *Store) canRun(j Job) error {
	if s.facts == nil {
		return errors.New("resource facts unavailable")
	}
	// Reuse the canonical policy decision instead of assuming unavailable power,
	// network or metering measurements are safe.
	f := s.facts()
	m := config.Mount{NetworkMode: j.NetworkMode, ChargingOnly: j.ChargingOnly, MinBatteryPercent: j.MinBatteryPercent}
	d := policy.Evaluate(m, f, s.now())
	if !d.Allowed {
		return fmt.Errorf("job resource policy blocked: %s", d.Reason)
	}
	return nil
}
func (s *Store) RunManual(name, proof string) (Run, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	j, e := s.job(name)
	if e != nil {
		return Run{}, e
	}
	b, _ := json.Marshal(j)
	if e = s.proofs.Consume(proof, previewproof.Binding{Action: "job.run", Subject: name, Revision: s.state.Registry.Revision, Digest: previewproof.Digest(b)}); e != nil {
		return Run{}, e
	}
	return s.claim(j)
}
func (s *Store) claim(j Job) (Run, error) {
	for _, r := range s.state.Runs {
		if r.Name == j.Name && r.State == "RUNNING" {
			return Run{}, errors.New("job already running")
		}
	}
	if e := s.canRun(j); e != nil {
		return Run{}, e
	}
	id := make([]byte, 16)
	if _, e := rand.Read(id); e != nil {
		return Run{}, e
	}
	r := Run{ID: hex.EncodeToString(id), Name: j.Name, State: "RUNNING", StartedUnix: s.now().Unix()}
	old := cloneState(s.state)
	s.state.Runs = append(s.state.Runs, r)
	if len(s.state.Runs) > 128 {
		s.state.Runs = s.state.Runs[len(s.state.Runs)-128:]
	}
	for i := range s.state.Registry.Jobs {
		if s.state.Registry.Jobs[i].Name == j.Name {
			s.state.Registry.Jobs[i].LastRunID = r.ID
			if j.IntervalSeconds > 0 {
				s.state.Registry.Jobs[i].NextUnix = s.now().Unix() + j.IntervalSeconds
			}
		}
	}
	// Durable claim is written before any process is executed. This prevents
	// duplicate due runs after a daemon crash (conservative at-most-once).
	if e := s.persist(); e != nil {
		s.state = old
		return Run{}, e
	}
	ctx, cancel := context.WithCancel(context.Background())
	s.running[r.ID] = cancel
	s.emit(r, "job.started", "running", "claimed")
	go s.execute(ctx, r.ID, j)
	return r, nil
}
func (s *Store) execute(ctx context.Context, id string, j Job) {
	var err error
	update := func(p DetailedProgress) {
		s.mu.Lock()
		defer s.mu.Unlock()
		for i := range s.state.Runs {
			r := &s.state.Runs[i]
			if r.ID != id {
				continue
			}
			if p.Bytes > r.Bytes {
				r.Bytes = p.Bytes
			}
			r.SpeedBytesPerSecond = p.Speed
			r.ETASeconds = p.ETA
			if p.TotalBytes != nil {
				r.TotalBytes = p.TotalBytes
			}
			if p.FilesDone != nil {
				r.FilesDone = p.FilesDone
			}
			if p.FilesTotal != nil {
				r.FilesTotal = p.FilesTotal
			}
			if p.ChecksDone != nil {
				r.ChecksDone = p.ChecksDone
			}
			if p.ChecksTotal != nil {
				r.ChecksTotal = p.ChecksTotal
			}
			if p.Errors != nil {
				r.Errors = p.Errors
			}
			if p.RetryError != nil {
				r.RetryError = p.RetryError
			}
			if p.TransferRetries != nil {
				r.TransferRetries = p.TransferRetries
			}
			r.Percent = nil
			if r.TotalBytes != nil && *r.TotalBytes > 0 {
				v := math.Min(100, (float64(r.Bytes)/float64(*r.TotalBytes))*100)
				r.Percent = &v
			}
			now := s.now()
			if last, seen := s.lastEmitted[id]; seen && now.Sub(last) < 2*time.Second {
				return
			}
			if err := s.persist(); err == nil {
				s.lastEmitted[id] = now
				s.emit(*r, "job.progress", "running", "transferring")
			}
			return
		}
	}
	if x, ok := s.executor.(DetailedProgressRunner); ok {
		err = x.ExecuteWithDetailedProgress(ctx, j, update)
	} else if x, ok := s.executor.(ProgressRunner); ok {
		err = x.ExecuteWithProgress(ctx, j, func(bytes int64, speed float64, eta int64) {
			update(DetailedProgress{Bytes: bytes, Speed: speed, ETA: eta})
		})
	} else {
		err = s.executor.Execute(ctx, j)
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	for i := range s.state.Runs {
		if s.state.Runs[i].ID == id {
			s.state.Runs[i].FinishedUnix = s.now().Unix()
			if ctx.Err() != nil {
				s.state.Runs[i].State = "CANCELLED"
				s.state.Runs[i].Reason = "user_cancelled"
			} else if err != nil {
				s.state.Runs[i].State = "FAILED"
				s.state.Runs[i].Reason = "executor_failed"
			} else {
				s.state.Runs[i].State = "COMPLETED"
			}
		}
	}
	delete(s.running, id)
	delete(s.cancelling, id)
	delete(s.lastEmitted, id)
	if s.persist() == nil {
		for _, r := range s.state.Runs {
			if r.ID == id {
				kind := "job.completed"
				phase := "finished"
				state := "completed"
				if r.State == "FAILED" {
					kind = "job.failed"
					state = "failed"
					phase = "executor_failed"
				}
				if r.State == "CANCELLED" {
					kind = "job.cancelled"
					state = "cancelled"
					phase = "user_cancelled"
				}
				s.emit(r, kind, state, phase)
				break
			}
		}
	}
}

func (s *Store) Cancel(id string) (Run, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	cancel, ok := s.running[id]
	if !ok {
		return Run{}, errors.New("no owned active run")
	}
	cancel()
	for _, r := range s.state.Runs {
		if r.ID == id && !s.cancelling[id] {
			s.cancelling[id] = true
			s.emit(r, "job.cancelling", "running", "cancellation_requested")
		}
	}
	for _, r := range s.state.Runs {
		if r.ID == id {
			return r, nil
		}
	}
	return Run{}, errors.New("missing run")
}
func (s *Store) Tick() (int, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	count := 0
	for _, j := range s.state.Registry.Jobs {
		if !j.Enabled || j.IntervalSeconds == 0 || j.NextUnix > s.now().Unix() {
			continue
		}
		if _, e := s.claim(j); e != nil {
			continue
		}
		count++
	}
	return count, nil
}

// RemoteTransfer is an ephemeral managed job: it is never added to the
// scheduled registry. Only non-deleting, non-overwriting copy and read-only
// check are offered in Phase B1. The source/destination must be configured
// remotes, checked separately through provider.Manager before both calls.
type RemoteTransfer struct {
	Kind        string `json:"kind"`
	Source      string `json:"source"`
	Destination string `json:"destination"`
}

func validRemoteTransfer(t RemoteTransfer) error {
	if t.Kind != "copy" && t.Kind != "check" {
		return errors.New("unsupported remote transfer kind")
	}
	if !validEndpoint(t.Source) || !validEndpoint(t.Destination) ||
		strings.HasPrefix(t.Source, "/") || strings.HasPrefix(t.Destination, "/") || t.Source == t.Destination {
		return errors.New("invalid remote transfer endpoints")
	}
	src := strings.SplitN(t.Source, ":", 2)
	dst := strings.SplitN(t.Destination, ":", 2)
	if src[1] == "" || dst[1] == "" {
		return errors.New("remote root transfers require a separate preview workflow")
	}
	if src[0] == dst[0] && (strings.HasPrefix(src[1], dst[1]+"/") || strings.HasPrefix(dst[1], src[1]+"/")) {
		return errors.New("overlapping source and destination folders")
	}
	return nil
}
func remoteTransferBinding(t RemoteTransfer, fingerprint string) previewproof.Binding {
	b, _ := json.Marshal(t)
	return previewproof.Binding{Action: "remote.transfer.start", Subject: "remote_transfer", Digest: previewproof.Digest(append(b, fingerprint...))}
}
func (s *Store) RemoteTransferPreview(t RemoteTransfer, configFingerprint string) (any, error) {
	if err := validRemoteTransfer(t); err != nil {
		return nil, err
	}
	if len(configFingerprint) != 64 {
		return nil, errors.New("remote configuration fingerprint missing")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	proof, err := s.proofs.Issue(remoteTransferBinding(t, configFingerprint), 2*time.Minute)
	if err != nil {
		return nil, err
	}
	return map[string]any{"proof": proof, "kind": t.Kind, "source": t.Source, "destination": t.Destination,
		"copies_skip_existing": t.Kind == "copy", "read_only": t.Kind == "check", "expires_seconds": 120}, nil
}
func (s *Store) RemoteTransferStart(t RemoteTransfer, fingerprint, proof string) (Run, error) {
	if err := validRemoteTransfer(t); err != nil {
		return Run{}, err
	}
	if len(fingerprint) != 64 {
		return Run{}, errors.New("remote configuration fingerprint missing")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if err := s.proofs.Consume(proof, remoteTransferBinding(t, fingerprint)); err != nil {
		return Run{}, err
	}
	if err := s.canRun(Job{NetworkMode: "any"}); err != nil {
		return Run{}, err
	}
	unique := make([]byte, 8)
	if _, err := rand.Read(unique); err != nil {
		return Run{}, err
	}
	j := Job{Name: "Remote" + hex.EncodeToString(unique), Kind: t.Kind, Source: t.Source, Destination: t.Destination,
		IgnoreExisting: t.Kind == "copy", Enabled: true, NetworkMode: "any"}
	return s.claim(j)
}
