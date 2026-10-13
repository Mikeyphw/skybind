package offline

import (
	"context"
	"crypto/md5"
	"encoding/hex"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"skybind/internal/mounts/config"
	"strings"
	"testing"
	"time"
)

type fakeRemote struct {
	files    map[string]string
	bad      bool
	changed  bool
	omitHash bool
	listing  []RemoteFile
}

func (f *fakeRemote) Run(_ context.Context, args ...string) ([]byte, error) {
	if len(args) < 2 {
		return nil, errors.New("bad args")
	}
	switch args[0] {
	case "lsjson":
		if args[1] == "--recursive" {
			return json.Marshal(f.listing)
		}
		path := args[len(args)-1]
		body, ok := f.files[path]
		if !ok {
			return nil, errors.New("missing")
		}
		sum := md5.Sum([]byte(body))
		hashes := map[string]string{"MD5": hex.EncodeToString(sum[:])}
		if f.bad {
			hashes["MD5"] = strings.Repeat("0", 32)
		}
		if f.omitHash {
			hashes = nil
		}
		stamp := "2026-10-13T00:00:00Z"
		if f.changed {
			stamp = "2026-10-14T00:00:00Z"
		}
		return json.Marshal(RemoteFile{Size: int64(len(body)), ModTime: stamp, Hashes: hashes})
	case "copyto":
		src, dst := args[len(args)-2], args[len(args)-1]
		body, ok := f.files[src]
		if !ok {
			return nil, errors.New("missing")
		}
		return nil, os.WriteFile(dst, []byte(body), 0600)
	}
	return nil, errors.New("unexpected command")
}
func fixture(t *testing.T) (*Store, *fakeRemote) {
	t.Helper()
	f := &fakeRemote{files: map[string]string{"drive:cloud/report.txt": "Complete offline contents", "drive:cloud/docs/a.txt": "alpha", "drive:cloud/docs/b.txt": "beta"}}
	store := New(filepath.Join(t.TempDir(), "offline"), f, func() (config.Registry, error) {
		return config.Registry{SchemaVersion: 2, Mounts: []config.Mount{{Name: "drive", Remote: "drive:cloud"}}}, nil
	})
	store.now = func() time.Time { return time.Unix(15, 0) }
	return store, f
}
func TestOfflinePinVerifyPersists(t *testing.T) {
	s, f := fixture(t)
	n, e := s.Pin(context.Background(), "drive", "report.txt", false)
	if e != nil || n != 1 {
		t.Fatalf("pin: n=%d err=%v", n, e)
	}
	st, e := s.Status(context.Background(), "drive", "report.txt", false)
	if e != nil || st.State != "AVAILABLE_OFFLINE" || st.Pin.Verification != "remote-hash+sha256" {
		t.Fatalf("status %+v %v", st, e)
	}
	s2 := New(s.dir, f, s.cfg)
	st, e = s2.Status(context.Background(), "drive", "report.txt", true)
	if e != nil || st.State != "AVAILABLE_OFFLINE" {
		t.Fatalf("reboot reopen: %+v %v", st, e)
	}
	f.changed = true
	st, e = s.Status(context.Background(), "drive", "report.txt", true)
	if e != nil || st.State != "STALE" {
		t.Fatalf("stale %+v %v", st, e)
	}
	f.changed = false
	local := filepath.Join(s.dir, "objects", st.Pin.SHA256)
	if e = os.WriteFile(local, []byte("tampered"), 0600); e != nil {
		t.Fatal(e)
	}
	st, e = s.Status(context.Background(), "drive", "report.txt", false)
	if e != nil || st.State != "CONFLICT" {
		t.Fatalf("conflict %+v %v", st, e)
	}
	if _, e = s.Export("drive", "report.txt"); e == nil {
		t.Fatal("tampered export allowed")
	}
}
func TestPinFailedHashNeverPublishes(t *testing.T) {
	s, f := fixture(t)
	f.bad = true
	if _, e := s.Pin(context.Background(), "drive", "report.txt", false); e == nil {
		t.Fatal("accepted mismatched provider checksum")
	}
	m, e := s.List()
	if e != nil || len(m.Pins) != 0 {
		t.Fatalf("published failed pin %v %+v", e, m)
	}
}
func TestOfflineUnknownRemoteHashHonest(t *testing.T) {
	s, f := fixture(t)
	f.omitHash = true
	if _, e := s.Pin(context.Background(), "drive", "report.txt", false); e != nil {
		t.Fatal(e)
	}
	m, e := s.List()
	if e != nil || m.Pins[0].Verification != "metadata+sha256" {
		t.Fatalf("provider proof misrepresented %+v %v", m, e)
	}
}
func TestOfflineDirectoryAndLimits(t *testing.T) {
	s, f := fixture(t)
	f.listing = []RemoteFile{{Path: "a.txt", Size: 5}, {Path: "b.txt", Size: 4}}
	n, e := s.Pin(context.Background(), "drive", "docs", true)
	if e != nil || n != 2 {
		t.Fatalf("dir pin %d %v", n, e)
	}
	m, e := s.List()
	if e != nil || len(m.Pins) != 2 {
		t.Fatalf("dir manifest %+v %v", m, e)
	}
	f.listing = []RemoteFile{{Path: "../config/rclone.conf", Size: 20}}
	if _, e := s.Pin(context.Background(), "drive", "docs", true); e == nil {
		t.Fatal("traversal accepted")
	}
	if _, e := s.Pin(context.Background(), "drive", "../private", false); e == nil {
		t.Fatal("traversal selection accepted")
	}
}
func TestOfflineManifestCorruptionFailsClosed(t *testing.T) {
	s, _ := fixture(t)
	if _, e := s.Pin(context.Background(), "drive", "report.txt", false); e != nil {
		t.Fatal(e)
	}
	file := filepath.Join(s.dir, "pins-v1.json")
	b, e := os.ReadFile(file)
	if e != nil {
		t.Fatal(e)
	}
	b = append(b, []byte("bad")...)
	if e = os.WriteFile(file, b, 0600); e != nil {
		t.Fatal(e)
	}
	// Strict envelope parsing must reject trailing garbage too.
	if _, e = s.List(); e == nil {
		t.Fatal("corrupted manifest was accepted")
	}
}
func TestOfflineQuotaAndUnpin(t *testing.T) {
	s, _ := fixture(t)
	if e := s.Quota(1 << 20); e != nil {
		t.Fatal(e)
	}
	if _, e := s.Pin(context.Background(), "drive", "report.txt", false); e != nil {
		t.Fatal(e)
	}
	if e := s.Unpin("drive", "report.txt"); e != nil {
		t.Fatal(e)
	}
	m, e := s.List()
	if e != nil || len(m.Pins) != 0 {
		t.Fatal("unpin not published", e)
	}
	n, e := s.GC()
	if e != nil || n != 1 {
		t.Fatalf("gc expected one orphan got %d %v", n, e)
	}
}
func TestOfflineDirectorySymlinkRejected(t *testing.T) {
	s, _ := fixture(t)
	if e := os.Symlink(t.TempDir(), s.dir); e != nil {
		t.Fatal(e)
	}
	if _, e := s.List(); e == nil {
		t.Fatal("symlink private root accepted")
	}
}
func TestOfflineBadSelections(t *testing.T) {
	s, _ := fixture(t)
	for _, v := range []string{"", "/root", "a/../b", "a//b", "a\\b", "a:b", "a/./b"} {
		if _, e := s.Pin(context.Background(), "drive", v, false); e == nil {
			t.Errorf("accepted path %q", v)
		}
	}
	if _, e := s.Pin(context.Background(), "../../evil", "report.txt", false); e == nil {
		t.Fatal("accepted bad mount")
	}
}

func TestOfflineQuotaProtectsRetainedOrphans(t *testing.T) {
	s, _ := fixture(t)
	if _, err := s.Pin(context.Background(), "drive", "report.txt", false); err != nil {
		t.Fatal(err)
	}
	if err := s.Unpin("drive", "report.txt"); err != nil {
		t.Fatal(err)
	}
	if err := s.Quota(1 << 20); err != nil {
		t.Fatal(err)
	}
	if _, err := s.Pin(context.Background(), "drive", "report.txt", false); err != nil {
		t.Fatal(err)
	}
}

// The single-file Downloads export must have the same identity protection as
// Status and M5C PublishView. This check precedes public path creation.
func TestExportRefusesStaleRemoteIdentityBeforePublicCopy(t *testing.T) {
	s, _ := fixture(t)
	if _, err := s.Pin(context.Background(), "drive", "report.txt", false); err != nil {
		t.Fatal(err)
	}
	s.cfg = func() (config.Registry, error) {
		return config.Registry{SchemaVersion: 2, Mounts: []config.Mount{{Name: "drive", Remote: "another:bucket"}}}, nil
	}
	st, err := s.Status(context.Background(), "drive", "report.txt", false)
	if err != nil || st.State != "STALE" {
		t.Fatalf("expected stale local pin: %+v %v", st, err)
	}
	if _, err := s.ExportContext(context.Background(), "drive", "report.txt"); err == nil || !strings.Contains(err.Error(), "stale") {
		t.Fatalf("stale pin export was not rejected before publication: %v", err)
	}
	s.cfg = func() (config.Registry, error) { return config.Registry{SchemaVersion: 2}, nil }
	if _, err := s.ExportContext(context.Background(), "drive", "report.txt"); err == nil || !strings.Contains(err.Error(), "stale") {
		t.Fatalf("removed mount export was not rejected: %v", err)
	}
}
