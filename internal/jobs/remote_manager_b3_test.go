package jobs

import (
	"os"
	"path/filepath"
	"skybind/internal/mounts/policy"
	"testing"
	"time"
)

func TestB3ExchangePathSafety(t *testing.T) {
	root := t.TempDir()
	if _, err := mediaPathUnder(root, "out/photos"); err != nil {
		t.Fatal(err)
	}
	bad := []string{"", ".", "..", "../secret", "file/../secret", "/proc", "hello//world", "folder\\name", "some:name", "folder\nother"}
	for _, name := range bad {
		if _, err := mediaPathUnder(root, name); err == nil {
			t.Errorf("accepted unsafe exchange subpath %q", name)
		}
	}
	if err := os.Symlink(t.TempDir(), filepath.Join(root, "trap")); err != nil {
		t.Fatal(err)
	}
	if _, err := mediaPathUnder(root, "trap/file"); err == nil {
		t.Fatal("escaped via exchange symlink")
	}
	if err := os.Mkdir(filepath.Join(root, "legit"), 0700); err != nil {
		t.Fatal(err)
	}
	if _, err := mediaPathUnder(root, "legit/incoming"); err != nil {
		t.Fatal(err)
	}
}
func TestB3FileMoveProofAndCancellation(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "jobs")
	if err := os.Mkdir(dir, 0700); err != nil {
		t.Fatal(err)
	}
	runner := b1Runner{entered: make(chan Job, 1), gate: make(chan struct{})}
	s, err := Open(dir, runner, func() policy.Facts { return policy.Facts{Network: policy.WiFi} })
	if err != nil {
		t.Fatal(err)
	}
	f := "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
	spec := RemoteFileMove{Source: "alpha:path/original.txt", Destination: "alpha:renamed/new.txt"}
	if validFileMove(RemoteFileMove{Source: "alpha:a", Destination: "beta:b"}) == nil {
		t.Fatal("allowed cross-remote move")
	}
	if validFileMove(RemoteFileMove{Source: "alpha:a", Destination: "alpha:a"}) == nil {
		t.Fatal("allowed no-op move")
	}
	prev, err := s.RemoteFileMovePreview(spec, f)
	if err != nil {
		t.Fatal(err)
	}
	proof := prev.(map[string]any)["proof"].(string)
	if _, err = s.RemoteFileMoveStart(spec, "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", proof); err == nil {
		t.Fatal("move started with stale file identity")
	}
	prev, err = s.RemoteFileMovePreview(spec, f)
	if err != nil {
		t.Fatal(err)
	}
	run, err := s.RemoteFileMoveStart(spec, f, prev.(map[string]any)["proof"].(string))
	if err != nil {
		t.Fatal(err)
	}
	j := <-runner.entered
	if j.Kind != "moveto" || !j.IgnoreExisting || j.Source != spec.Source || j.Destination != spec.Destination {
		t.Fatalf("unsafe moved job: %+v", j)
	}
	if _, err = s.Cancel(run.ID); err != nil {
		t.Fatal(err)
	}
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		status, e := s.RunStatus(run.ID)
		if e == nil && status.State == "CANCELLED" {
			break
		}
		time.Sleep(5 * time.Millisecond)
	}
	status, _ := s.RunStatus(run.ID)
	if status.State != "CANCELLED" {
		t.Fatalf("cancel not persisted: %s", status.State)
	}
	if _, err = s.RemoteFileMoveStart(spec, f, prev.(map[string]any)["proof"].(string)); err == nil {
		t.Fatal("move proof replay")
	}
	if err = execMoveGuard(Job{Kind: "moveto", Source: "alpha:a", Destination: "beta:b", IgnoreExisting: true}); err == nil {
		t.Fatal("incorrect move guard")
	}

}
