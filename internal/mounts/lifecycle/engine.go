// Package lifecycle owns FUSE process identity, observation and deliberate stops.
// The CLI never controls PIDs, executable paths or raw mount arguments.
package lifecycle

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"skybind/internal/atomicfile"
	"skybind/internal/mounts/cache"
	"skybind/internal/mounts/config"
	"skybind/internal/mounts/policy"
	"skybind/internal/paths"
	"skybind/internal/previewproof"
	"skybind/internal/runtimeauth"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"
)

var nameRE = regexp.MustCompile(`^[a-zA-Z][a-zA-Z0-9_-]{0,62}$`)

type Ownership struct {
	Name        string `json:"name"`
	PID         int    `json:"pid"`
	StartTicks  uint64 `json:"start_ticks"`
	Executable  string `json:"executable"`
	Mountpoint  string `json:"mountpoint"`
	CreatedUnix int64  `json:"created_unix"`
	MountID     string `json:"mount_id"`
}
type State struct {
	Name     string `json:"name"`
	Desired  bool   `json:"desired"`
	Observed string `json:"observed"`
	Reason   string `json:"reason"`
	PID      int    `json:"pid,omitempty"`
}
type MountObservation struct {
	Point   string
	FsType  string
	Source  string
	MountID string
}
type Observer interface {
	Identity(pid int) (uint64, string, error)
	Mount(point string) (MountObservation, bool, error)
}
type Spawner interface {
	Start(binary string, args []string) (int, error)
	Stop(pid int) error
	Unmount(helper, point string) error
}
type RunEnv interface {
	RuntimeReady() bool
	Facts() policy.Facts
	Now() time.Time
}
type linuxObserver struct{}
type linuxSpawner struct{}
type canonicalEnvironment struct{}

func (canonicalEnvironment) RuntimeReady() bool { return runtimeauth.StatusCanonical().Ready }
func (canonicalEnvironment) Facts() policy.Facts {
	return policy.SampleAndroidFacts(filepath.Join(paths.StateRoot, "cache"))
}
func (canonicalEnvironment) Now() time.Time { return time.Now() }
func (linuxSpawner) Start(binary string, args []string) (int, error) {
	c := exec.Command(binary, args...)
	c.Stdin = nil
	c.Stdout = nil
	c.Stderr = nil
	c.Env = []string{"PATH=/system/bin:/system/xbin"}
	if e := c.Start(); e != nil {
		return 0, e
	}
	go func() { _ = c.Wait() }()
	return c.Process.Pid, nil
}

// pidfd pins process identity across PID recycling. Never fall back to
// kill(pid): an unsupported kernel must fail closed rather than signal a
// coincidentally reused process.
func (linuxSpawner) Stop(pid int) error {
	if pid <= 0 {
		return errors.New("invalid PID")
	}
	const pidfdOpen = 434
	const pidfdSendSignal = 424
	fd, _, errno := syscall.Syscall(pidfdOpen, uintptr(pid), 0, 0)
	if errno != 0 {
		return errno
	}
	defer syscall.Close(int(fd))
	_, _, errno = syscall.Syscall6(pidfdSendSignal, fd, uintptr(syscall.SIGTERM), 0, 0, 0, 0)
	if errno != 0 {
		return errno
	}
	return nil
}
func (linuxSpawner) Unmount(helper, point string) error {
	c := exec.Command(helper, "-u", point)
	c.Env = []string{"PATH=/system/bin:/system/xbin"}
	return c.Run()
}
func (linuxObserver) Identity(pid int) (uint64, string, error) {
	b, e := os.ReadFile(fmt.Sprintf("/proc/%d/stat", pid))
	if e != nil {
		return 0, "", e
	}
	tail := string(b)
	end := strings.LastIndex(tail, ")")
	if end < 0 {
		return 0, "", errors.New("bad /proc stat")
	}
	fields := strings.Fields(tail[end+1:])
	if len(fields) < 20 {
		return 0, "", errors.New("truncated proc stat")
	}
	start, e := strconv.ParseUint(fields[19], 10, 64)
	if e != nil {
		return 0, "", e
	}
	exe, e := os.Readlink(fmt.Sprintf("/proc/%d/exe", pid))
	return start, exe, e
}
func decodeMountField(s string) string {
	r := strings.NewReplacer(`\040`, ` `, `\011`, `\t`, `\012`, `\n`, `\134`, `\`)
	return r.Replace(s)
}
func (linuxObserver) Mount(point string) (MountObservation, bool, error) {
	b, e := os.ReadFile("/proc/self/mountinfo")
	if e != nil {
		return MountObservation{}, false, e
	}
	for _, line := range strings.Split(string(b), "\n") {
		parts := strings.SplitN(line, " - ", 2)
		if len(parts) != 2 {
			continue
		}
		l := strings.Fields(parts[0])
		r := strings.Fields(parts[1])
		if len(l) < 5 || len(r) < 2 {
			continue
		}
		if decodeMountField(l[4]) == point {
			return MountObservation{Point: point, FsType: r[0], Source: r[1], MountID: l[0]}, true, nil
		}
	}
	return MountObservation{}, false, nil
}

type Engine struct {
	mu        sync.Mutex
	store     *config.Store
	dir       string
	obs       Observer
	run       Spawner
	env       RunEnv
	state     map[string]bool
	proofs    *previewproof.Store
	rcPrepare func(string) ([]string, error)
	rcDrop    func(string)
}

// Canonical returns a production engine. Roots and executables cannot be
// supplied by clients; only tests in Go can construct injected fixtures.
func Canonical(s *config.Store) *Engine {
	return newEngine(s, filepath.Join(paths.StateRoot, "desired"), linuxObserver{}, linuxSpawner{}, canonicalEnvironment{})
}
func newEngine(s *config.Store, dir string, o Observer, r Spawner, env RunEnv) *Engine {
	return &Engine{store: s, dir: dir, obs: o, run: r, env: env, state: map[string]bool{}, proofs: previewproof.New()}
}

// ConfigureRC attaches a per-mount authenticated loopback endpoint provider.
// Only the root-owned daemon may configure this hook; no request may supply flags.
func (e *Engine) ConfigureRC(prepare func(string) ([]string, error), drop func(string)) {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.rcPrepare = prepare
	e.rcDrop = drop
}
func (e *Engine) recordFile(name string) string { return filepath.Join(e.dir, "process-"+name+".json") }
func (e *Engine) desiredFile() string           { return filepath.Join(e.dir, "desired-v1.json") }
func (e *Engine) loadDesired() error {
	b, err := atomicfile.Read(e.dir, "desired-v1.json", 65536)
	if os.IsNotExist(err) {
		return nil
	}
	if err != nil {
		return err
	}
	var v map[string]bool
	if err = json.Unmarshal(b, &v); err != nil {
		return err
	}
	for k := range v {
		if !nameRE.MatchString(k) {
			return errors.New("invalid persisted desired mount")
		}
	}
	e.state = v
	return nil
}
func (e *Engine) persistDesired() error {
	b, err := json.Marshal(e.state)
	if err != nil {
		return err
	}
	return atomicfile.Write(e.dir, "desired-v1.json", b)
}
func (e *Engine) getMount(name string) (config.Mount, error) {
	if !nameRE.MatchString(name) {
		return config.Mount{}, errors.New("invalid mount name")
	}
	if e.store == nil {
		return config.Mount{}, errors.New("registry unavailable")
	}
	r, err := e.store.Snapshot()
	if err != nil {
		return config.Mount{}, err
	}
	for _, m := range r.Mounts {
		if m.Name == name {
			return m, nil
		}
	}
	return config.Mount{}, errors.New("mount not configured")
}
func (e *Engine) List() ([]string, error) {
	r, err := e.store.Snapshot()
	if err != nil {
		return nil, err
	}
	names := make([]string, 0, len(r.Mounts))
	for _, m := range r.Mounts {
		names = append(names, m.Name)
	}
	return names, nil
}
func (e *Engine) owned(m config.Mount) (Ownership, bool, error) {
	b, err := atomicfile.Read(e.dir, "process-"+m.Name+".json", 4096)
	if os.IsNotExist(err) {
		return Ownership{}, false, nil
	}
	if err != nil {
		return Ownership{}, false, err
	}
	var rec Ownership
	if len(b) > 4096 || json.Unmarshal(b, &rec) != nil {
		return Ownership{}, false, errors.New("invalid ownership record")
	}
	if rec.Name != m.Name || rec.Mountpoint != m.Mountpoint || rec.Executable != paths.Engine || rec.PID <= 0 || rec.StartTicks == 0 {
		return Ownership{}, false, errors.New("ownership mismatch")
	}
	tick, exe, err := e.obs.Identity(rec.PID)
	if err != nil {
		return rec, false, nil
	}
	if tick != rec.StartTicks || exe != rec.Executable {
		return rec, false, errors.New("process identity drift")
	}
	return rec, true, nil
}
func (e *Engine) inspect(m config.Mount) (State, error) {
	s := State{Name: m.Name, Desired: e.state[m.Name], Observed: "STOPPED", Reason: "not_running"}
	rec, owned, err := e.owned(m)
	if err != nil {
		s.Observed = "DEGRADED"
		s.Reason = err.Error()
		return s, err
	}
	v, exists, err := e.obs.Mount(m.Mountpoint)
	if err != nil {
		return s, err
	}
	if exists && (!owned || !strings.HasPrefix(v.FsType, "fuse") || rec.MountID == "" || rec.MountID != v.MountID) {
		s.Observed = "MOUNT_STALE"
		s.Reason = "unowned_or_wrong_filesystem"
		return s, errors.New(s.Reason)
	}
	if owned {
		s.PID = rec.PID
		if exists {
			s.Observed = "RUNNING"
			s.Reason = "owned_fuse_mount"
		} else {
			s.Observed = "DEGRADED"
			s.Reason = "process_without_fuse_mount"
		}
	}
	return s, nil
}
func (e *Engine) Status(name string) (State, error) {
	e.mu.Lock()
	defer e.mu.Unlock()
	if err := e.loadDesired(); err != nil {
		return State{}, err
	}
	m, err := e.getMount(name)
	if err != nil {
		return State{}, err
	}
	return e.inspect(m)
}

// VerifiedMount returns a source mount only after full process, FUSE and
// mountinfo identity checks. It is the sole authority for namespace binds.
func (e *Engine) VerifiedMount(name string) (Ownership, MountObservation, error) {
	e.mu.Lock()
	defer e.mu.Unlock()
	m, err := e.getMount(name)
	if err != nil {
		return Ownership{}, MountObservation{}, err
	}
	state, err := e.inspect(m)
	if err != nil || state.Observed != "RUNNING" {
		return Ownership{}, MountObservation{}, errors.New("source mount not verified running")
	}
	rec, owned, err := e.owned(m)
	if err != nil || !owned {
		return Ownership{}, MountObservation{}, errors.New("source process ownership missing")
	}
	observed, exists, err := e.obs.Mount(m.Mountpoint)
	if err != nil || !exists || rec.MountID != observed.MountID || !strings.HasPrefix(observed.FsType, "fuse") {
		return Ownership{}, MountObservation{}, errors.New("source FUSE signature drift")
	}
	return rec, observed, nil
}

func (e *Engine) Preview(name string) (map[string]any, error) {
	e.mu.Lock()
	defer e.mu.Unlock()
	m, err := e.getMount(name)
	if err != nil {
		return nil, err
	}
	if !m.Enabled {
		return nil, errors.New("mount disabled")
	}
	p, err := policy.Resolve(m)
	if err != nil {
		return nil, err
	}
	dec := policy.Evaluate(m, e.env.Facts(), e.env.Now())
	revision, err := e.store.Snapshot()
	if err != nil {
		return nil, err
	}
	b, _ := json.Marshal(m)
	hash := sha256.Sum256(b)
	proof, err := e.proofs.Issue(previewproof.Binding{Action: "mount.start", Subject: name, Revision: revision.Revision, Digest: hex.EncodeToString(hash[:])}, 2*time.Minute)
	if err != nil {
		return nil, err
	}
	return map[string]any{"proof": proof, "mount": m.Name, "mountpoint": m.Mountpoint, "remote": m.Remote, "profile": p, "resource_decision": dec, "runtime_verified": e.env.RuntimeReady(), "device_qualified": false}, nil
}

// StartGuarded is the user-facing mutation gate; the supervisor uses trusted
// internal Start() after persisted desired state and resource decisions.
func (e *Engine) StartGuarded(name, proof string) (State, error) {
	m, err := e.getMount(name)
	if err != nil {
		return State{}, err
	}
	r, err := e.store.Snapshot()
	if err != nil {
		return State{}, err
	}
	b, _ := json.Marshal(m)
	h := sha256.Sum256(b)
	if err = e.proofs.Consume(proof, previewproof.Binding{Action: "mount.start", Subject: name, Revision: r.Revision, Digest: hex.EncodeToString(h[:])}); err != nil {
		return State{}, err
	}
	return e.Start(name)
}

// verifyDestination traverses each existing directory component without
// following links. A symlinked storage alias requires explicit Android topology
// handling in SB-C02, not an unchecked mount operation.
func verifyDestination(dest string) error {
	if !filepath.IsAbs(dest) || filepath.Clean(dest) != dest {
		return errors.New("invalid mount destination")
	}
	cur := "/"
	for _, part := range strings.Split(strings.TrimPrefix(dest, "/"), "/") {
		if part == "" || part == "." || part == ".." {
			return errors.New("invalid mount destination component")
		}
		cur = filepath.Join(cur, part)
		st, err := os.Lstat(cur)
		if err != nil {
			return err
		}
		if st.Mode()&os.ModeSymlink != 0 || !st.IsDir() {
			return errors.New("destination contains link/non-directory")
		}
	}
	return nil
}
func buildArgs(m config.Mount, cacheDir string) ([]string, error) {
	p, err := policy.Resolve(m)
	if err != nil {
		return nil, err
	}
	if !filepath.IsAbs(m.Mountpoint) || filepath.Clean(m.Mountpoint) != m.Mountpoint {
		return nil, errors.New("invalid destination")
	}
	mode := p.CacheMode
	if mode == "" {
		mode = "off"
	}
	level := m.LogLevel
	if level == "" {
		level = "NOTICE"
	}
	args := []string{"mount", m.Remote, m.Mountpoint, "--config", paths.RcloneConfig, "--vfs-cache-mode", mode, "--vfs-cache-max-size", strconv.FormatInt(p.MaxBytes, 10), "--vfs-cache-max-age", time.Duration(p.MaxAgeSeconds * int64(time.Second)).String(), "--dir-cache-time", time.Duration(p.DirCacheSeconds * int64(time.Second)).String(), "--poll-interval", time.Duration(p.PollSeconds * int64(time.Second)).String(), "--cache-dir", cacheDir, "--log-level", level}
	if m.AllowOther {
		args = append(args, "--allow-other")
	}
	if m.ReadOnly {
		args = append(args, "--read-only")
	}
	return args, nil
}
func (e *Engine) Start(name string) (State, error) {
	e.mu.Lock()
	defer e.mu.Unlock()
	if err := e.loadDesired(); err != nil {
		return State{}, err
	}
	m, err := e.getMount(name)
	if err != nil {
		return State{}, err
	}
	if !m.Enabled {
		return State{}, errors.New("mount disabled")
	}
	if !e.env.RuntimeReady() {
		return State{}, errors.New("static runtime integrity unverified")
	}
	dec := policy.Evaluate(m, e.env.Facts(), e.env.Now())
	if !dec.Allowed {
		return State{}, fmt.Errorf("resource policy blocked: %s", dec.Reason)
	}
	s, err := e.inspect(m)
	if err != nil {
		return s, err
	}
	if s.Observed == "RUNNING" {
		return s, nil
	}
	if s.Observed == "DEGRADED" {
		return s, errors.New("stale owned process requires recovery")
	}
	if err = os.MkdirAll(e.dir, 0700); err != nil {
		return State{}, err
	}
	if e.dir == filepath.Join(paths.StateRoot, "desired") {
		if err = verifyDestination(m.Mountpoint); err != nil {
			return State{}, err
		}
		if err = cache.EnsureCanonical(name); err != nil {
			return State{}, err
		}
	}
	args, err := buildArgs(m, filepath.Join(paths.StateRoot, "cache", m.Name))
	if err != nil {
		return State{}, err
	}
	if e.rcPrepare != nil {
		options, rerr := e.rcPrepare(name)
		if rerr != nil {
			return State{}, rerr
		}
		args = append(args, options...)
	}
	pid, err := e.run.Start(paths.Engine, args)
	if err != nil {
		if e.rcDrop != nil {
			e.rcDrop(name)
		}
		return State{}, err
	}
	tick, exe, err := e.obs.Identity(pid)
	if err != nil || exe != paths.Engine || tick == 0 {
		if pid > 0 {
			_ = e.run.Stop(pid)
		}
		if e.rcDrop != nil {
			e.rcDrop(name)
		}
		return State{}, errors.New("could not prove child process ownership")
	}
	// Do not assert readiness until the observed mount exists and has a stable
	// mountinfo identity. Future namespace visibility is a separate device gate.
	var observed MountObservation
	verified := false
	for i := 0; i < 20; i++ {
		v, exists, obErr := e.obs.Mount(m.Mountpoint)
		if obErr == nil && exists && strings.HasPrefix(v.FsType, "fuse") && v.MountID != "" {
			observed = v
			verified = true
			break
		}
		time.Sleep(100 * time.Millisecond)
	}
	if !verified {
		_ = e.run.Stop(pid)
		if e.rcDrop != nil {
			e.rcDrop(name)
		}
		return State{}, errors.New("FUSE readiness/mount identity not observed")
	}
	rec := Ownership{Name: m.Name, PID: pid, StartTicks: tick, Executable: exe, Mountpoint: m.Mountpoint, MountID: observed.MountID, CreatedUnix: e.env.Now().Unix()}
	buf, _ := json.Marshal(rec)
	if err = atomicfile.Write(e.dir, "process-"+name+".json", buf); err != nil {
		_ = e.run.Stop(pid)
		if e.rcDrop != nil {
			e.rcDrop(name)
		}
		return State{}, err
	}
	e.state[name] = true
	if err = e.persistDesired(); err != nil {
		return State{}, err
	}
	return e.inspect(m)
}
func (e *Engine) Stop(name string) (State, error) {
	e.mu.Lock()
	defer e.mu.Unlock()
	if err := e.loadDesired(); err != nil {
		return State{}, err
	}
	m, err := e.getMount(name)
	if err != nil {
		return State{}, err
	}
	rec, owned, err := e.owned(m)
	if err != nil {
		return State{}, err
	}
	v, exists, err := e.obs.Mount(m.Mountpoint)
	if err != nil {
		return State{}, err
	}
	if exists && (!owned || !strings.HasPrefix(v.FsType, "fuse") || rec.MountID == "" || rec.MountID != v.MountID) {
		return State{}, errors.New("refuse unowned mount detach")
	}
	e.state[name] = false
	if err = e.persistDesired(); err != nil {
		return State{}, err
	}
	if owned {
		if exists {
			// Revalidate the process before attempting a mount detach.
			tick, exe, identityErr := e.obs.Identity(rec.PID)
			if identityErr != nil || tick != rec.StartTicks || exe != rec.Executable {
				return State{}, errors.New("owned process identity lost before unmount")
			}
			if err = e.run.Unmount(paths.FuseHelper, m.Mountpoint); err != nil {
				return State{}, err
			}
		}
		if tick, exe, identityErr := e.obs.Identity(rec.PID); identityErr == nil && (tick != rec.StartTicks || exe != rec.Executable) {
			return State{}, errors.New("process identity changed before SIGTERM")
		}
		if err = e.run.Stop(rec.PID); err != nil && !errors.Is(err, syscall.ESRCH) {
			return State{}, err
		}
		_ = os.Remove(e.recordFile(name))
	}
	if e.rcDrop != nil {
		e.rcDrop(name)
	}
	return e.inspect(m)
}
func (e *Engine) Restart(name string) (State, error) {
	if _, err := e.Stop(name); err != nil {
		return State{}, err
	}
	return e.Start(name)
}
func (e *Engine) Desired(name string) (bool, error) {
	e.mu.Lock()
	defer e.mu.Unlock()
	if err := e.loadDesired(); err != nil {
		return false, err
	}
	return e.state[name], nil
}
func (e *Engine) Reconcile(ctx context.Context) ([]State, error) {
	names, err := e.List()
	if err != nil {
		return nil, err
	}
	out := []State{}
	for _, name := range names {
		if ctx.Err() != nil {
			return out, ctx.Err()
		}
		desired, err := e.Desired(name)
		if err != nil {
			return out, err
		}
		var s State
		if desired {
			s, err = e.Start(name)
		} else {
			s, err = e.Status(name)
		}
		out = append(out, s)
		if err != nil {
			return out, err
		}
	}
	return out, nil
}
