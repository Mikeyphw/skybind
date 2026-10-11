package lifecycle

import (
	"encoding/json"
	"os"
	"path/filepath"
	"skybind/internal/mounts/config"
	"skybind/internal/mounts/policy"
	"testing"
	"time"
)

type fakeObserver struct {
	pid     int
	tick    uint64
	exe     string
	mounted bool
	fs      string
	mountID string
}

func (f *fakeObserver) Identity(pid int) (uint64, string, error) {
	if pid != f.pid {
		return 0, "", os.ErrNotExist
	}
	return f.tick, f.exe, nil
}
func (f *fakeObserver) Mount(point string) (MountObservation, bool, error) {
	return MountObservation{Point: point, FsType: f.fs, MountID: func() string {
		if f.mountID != "" {
			return f.mountID
		}
		return "42"
	}()}, f.mounted, nil
}

type fakeRunner struct {
	f        *fakeObserver
	starts   int
	stops    int
	unmounts int
}

func (f *fakeRunner) Start(binary string, args []string) (int, error) {
	f.starts++
	f.f.pid = 73
	f.f.tick = 203
	f.f.exe = binary
	f.f.mounted = true
	f.f.fs = "fuse.rclone"
	return 73, nil
}
func (f *fakeRunner) Stop(int) error               { f.stops++; f.f.pid = 0; return nil }
func (f *fakeRunner) Unmount(string, string) error { f.unmounts++; f.f.mounted = false; return nil }

type fakeEnv struct {
	ready bool
	facts policy.Facts
}

func (f fakeEnv) RuntimeReady() bool  { return f.ready }
func (f fakeEnv) Facts() policy.Facts { return f.facts }
func (f fakeEnv) Now() time.Time      { return time.Now() }
func mountFixture(t *testing.T) (*Engine, *fakeObserver, *fakeRunner) {
	t.Helper()
	base := t.TempDir()
	cfgDir := filepath.Join(base, "config")
	stateDir := filepath.Join(base, "desired")
	for _, p := range []string{cfgDir, stateDir} {
		if e := os.Mkdir(p, 0700); e != nil {
			t.Fatal(e)
		}
	}
	cfg, e := config.Open(cfgDir)
	if e != nil {
		t.Fatal(e)
	}
	r := config.Empty()
	r.Mounts = []config.Mount{{Name: "cloud", Remote: "example:/", Mountpoint: "/mnt/cloud", Enabled: true, NetworkMode: "offline-allowed", VFSProfile: "balanced"}}
	raw, _ := json.Marshal(r)
	proof, e := cfg.Preview(raw)
	if e != nil {
		t.Fatal(e)
	}
	if _, e = cfg.Apply(raw, proof.Token); e != nil {
		t.Fatal(e)
	}
	f := &fakeObserver{}
	run := &fakeRunner{f: f}
	return newEngine(cfg, stateDir, f, run, fakeEnv{ready: true}), f, run
}
func TestStartStopAndExplicitStopPersistence(t *testing.T) {
	e, f, r := mountFixture(t)
	s, err := e.Start("cloud")
	if err != nil || s.Observed != "RUNNING" {
		t.Fatalf("start: %+v %v", s, err)
	}
	s, err = e.Stop("cloud")
	if err != nil || r.stops != 1 || r.unmounts != 1 {
		t.Fatalf("stop: %+v %v", s, err)
	}
	desired, e2 := e.Desired("cloud")
	if e2 != nil || desired {
		t.Fatal("explicit stop lost")
	}
	f.mounted = false
}
func TestPidReuseAndForeignFuseRefused(t *testing.T) {
	e, f, _ := mountFixture(t)
	if _, err := e.Start("cloud"); err != nil {
		t.Fatal(err)
	}
	f.tick = 204
	if _, err := e.Stop("cloud"); err == nil {
		t.Fatal("stopped replaced PID")
	}
}
func TestExternalMountNeverUnlinked(t *testing.T) {
	e, f, r := mountFixture(t)
	f.mounted = true
	f.fs = "ext4"
	if _, err := e.Stop("cloud"); err == nil {
		t.Fatal("external filesystem detached")
	}
	if r.unmounts != 0 {
		t.Fatal("ran unmount")
	}
}
func TestUnverifiedRuntimeRefused(t *testing.T) {
	e, _, r := mountFixture(t)
	e.env = fakeEnv{ready: false}
	if _, err := e.Start("cloud"); err == nil {
		t.Fatal("unverified runtime started")
	}
	if r.starts != 0 {
		t.Fatal("spawned")
	}
}
func TestArgsNeverTakeRawClientFlags(t *testing.T) {
	m := config.Mount{Name: "cloud", Mountpoint: "/mnt/Cloud", Remote: "remote:/", VFSProfile: "balanced", ReadOnly: true}
	args, e := buildArgs(m, "/data/adb/skybind/cache/cloud")
	if e != nil {
		t.Fatal(e)
	}
	if len(args) < 4 || args[0] != "mount" || args[1] != "remote:/" {
		t.Fatal(args)
	}
}
func TestStartProofSingleUse(t *testing.T) {
	e, _, _ := mountFixture(t)
	p, err := e.Preview("cloud")
	if err != nil {
		t.Fatal(err)
	}
	proof, ok := p["proof"].(string)
	if !ok || len(proof) != 64 {
		t.Fatal("missing preview proof")
	}
	if _, err = e.StartGuarded("cloud", proof); err != nil {
		t.Fatal(err)
	}
	if _, err = e.StartGuarded("cloud", proof); err == nil {
		t.Fatal("reused start proof")
	}
}
func TestMountIdentityChangeRefused(t *testing.T) {
	e, f, r := mountFixture(t)
	if _, err := e.Start("cloud"); err != nil {
		t.Fatal(err)
	}
	f.fs = "ext4"
	if _, err := e.Stop("cloud"); err == nil {
		t.Fatal("unmounted changed filesystem")
	}
	if r.unmounts > 0 {
		t.Fatal("detached foreign mount")
	}
}
func TestUnverifiedForeignPIDNeverSignaled(t *testing.T) {
	e, f, r := mountFixture(t)
	if _, err := e.Start("cloud"); err != nil {
		t.Fatal(err)
	}
	f.tick++
	if _, err := e.Stop("cloud"); err == nil {
		t.Fatal("PID reuse not rejected")
	}
	if r.stops != 0 || r.unmounts != 0 {
		t.Fatal("targeted foreign PID/mount")
	}
}
func TestMountpointSymlinkRefused(t *testing.T) {
	base := t.TempDir()
	real := filepath.Join(base, "real")
	os.Mkdir(real, 0700)
	alias := filepath.Join(base, "alias")
	os.Symlink(real, alias)
	if err := verifyDestination(alias); err == nil {
		t.Fatal("symlink mountpoint accepted")
	}
	if err := verifyDestination(real); err != nil {
		t.Fatal(err)
	}
}

func TestDifferentFUSEMountIDRefused(t *testing.T) {
	e, f, r := mountFixture(t)
	if _, err := e.Start("cloud"); err != nil {
		t.Fatal(err)
	}
	f.mountID = "999"
	if _, err := e.Stop("cloud"); err == nil {
		t.Fatal("replaced FUSE mount was detached")
	}
	if r.unmounts != 0 {
		t.Fatal("unmounted replaced FUSE mount")
	}
}
