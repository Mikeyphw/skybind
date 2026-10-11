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
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"skybind/internal/atomicfile"
	"skybind/internal/mounts/config"
	"skybind/internal/mounts/policy"
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
}
type Registry struct {
	SchemaVersion int    `json:"schema_version"`
	Revision      uint64 `json:"revision"`
	Jobs          []Job  `json:"jobs"`
}
type Run struct {
	ID                  string  `json:"id"`
	Name                string  `json:"name"`
	State               string  `json:"state"`
	StartedUnix         int64   `json:"started_unix"`
	FinishedUnix        int64   `json:"finished_unix,omitempty"`
	Reason              string  `json:"reason,omitempty"`
	Bytes               int64   `json:"bytes,omitempty"`
	SpeedBytesPerSecond float64 `json:"speed_bytes_per_second,omitempty"`
	ETASeconds          int64   `json:"eta_seconds,omitempty"`
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

func (r execRunner) Execute(ctx context.Context, j Job) error {
	return r.ExecuteWithProgress(ctx, j, nil)
}
func (execRunner) ExecuteWithProgress(ctx context.Context, j Job, update func(int64, float64, int64)) error {
	if err := validateLocalExisting(j.Source); err != nil {
		return err
	}
	if err := validateLocalExisting(j.Destination); err != nil {
		return err
	}
	args := []string{"--config", paths.RcloneConfig, j.Kind, j.Source, j.Destination, "--stats", "1s", "--stats-log-level", "NOTICE", "--use-json-log", "--log-level", "NOTICE"}
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
			if bytes, rate, eta, ok := decodeStats(scanner.Bytes()); ok {
				update(bytes, rate, eta)
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
	var obj map[string]json.RawMessage
	if len(line) > 65536 || json.Unmarshal(line, &obj) != nil {
		return 0, 0, 0, false
	}
	stats := obj
	if raw, ok := obj["stats"]; ok {
		if json.Unmarshal(raw, &stats) != nil {
			return 0, 0, 0, false
		}
	}
	var transferred int64
	var speed float64
	var eta int64
	if raw := stats["bytes"]; raw != nil {
		_ = json.Unmarshal(raw, &transferred)
	}
	if raw := stats["speed"]; raw != nil {
		_ = json.Unmarshal(raw, &speed)
	}
	if raw := stats["eta"]; raw != nil {
		_ = json.Unmarshal(raw, &eta)
	}
	if transferred < 0 || speed < 0 || speed > 1e15 || eta < 0 || eta > 1<<40 {
		return 0, 0, 0, false
	}
	if transferred == 0 && speed == 0 {
		return 0, 0, 0, false
	}
	return transferred, speed, eta, true
}

type Store struct {
	mu       sync.Mutex
	dir      string
	state    persisted
	proofs   *previewproof.Store
	executor Executor
	running  map[string]context.CancelFunc
	now      func() time.Time
	facts    func() policy.Facts
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
	s := &Store{dir: dir, proofs: previewproof.New(), executor: executor, running: map[string]context.CancelFunc{}, now: time.Now, facts: facts}
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
func clone(r Registry) Registry { r.Jobs = append([]Job(nil), r.Jobs...); return r }

// RunStatus returns only a previously claimed job run; it cannot launch work.
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
	return map[string]any{"registry": clone(s.state.Registry), "runs": append([]Run(nil), s.state.Runs...)}, nil
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
	go s.execute(ctx, r.ID, j)
	return r, nil
}
func (s *Store) execute(ctx context.Context, id string, j Job) {
	var err error
	if x, ok := s.executor.(ProgressRunner); ok {
		err = x.ExecuteWithProgress(ctx, j, func(bytes int64, speed float64, eta int64) {
			s.mu.Lock()
			defer s.mu.Unlock()
			for i := range s.state.Runs {
				if s.state.Runs[i].ID == id {
					if bytes < s.state.Runs[i].Bytes {
						return
					}
					s.state.Runs[i].Bytes = bytes
					s.state.Runs[i].SpeedBytesPerSecond = speed
					s.state.Runs[i].ETASeconds = eta
					_ = s.persist()
					return
				}
			}
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
	_ = s.persist()
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
