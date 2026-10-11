package lifecycle

import (
	"strings"
	"testing"
)

func TestMountStderrBoundedAndCategorized(t *testing.T) {
	tests := []struct{ raw, expected string }{
		{"Fatal error: fusermount3: operation not permitted, token=private", "provider_permission_denied"},
		{"error: /dev/fuse not found", "fuse_device_unavailable"},
		{"Fatal: directory not empty", "mountpoint_not_empty"},
		{"Fatal error: failed to create file system for SafeGDrive: private details", "provider_remote_failure"},
		{"random API response token=private-data", "provider_stderr_unclassified"},
		{"", "provider_no_stderr_observed"},
	}
	for _, tc := range tests {
		capture := &mountStderr{}
		if _, err := capture.Write([]byte(tc.raw)); err != nil {
			t.Fatal(err)
		}
		if got := capture.hint(); got != tc.expected {
			t.Errorf("expected %s got %s", tc.expected, got)
		}
		if strings.Contains(capture.hint(), "private") {
			t.Fatal("captured secret surfaced")
		}
	}
	capture := &mountStderr{}
	capture.Write([]byte(strings.Repeat("x", 10000)))
	if len(capture.data) > maxMountStderrBytes {
		t.Fatal("unbounded capture")
	}
}

type mountNeverAppears struct {
	observer *fakeObserver
	stopped  bool
}

func (s *mountNeverAppears) Start(binary string, _ []string) (int, error) {
	s.observer.pid = 88
	s.observer.tick = 456
	s.observer.exe = binary
	s.observer.mounted = false
	return 88, nil
}
func (s *mountNeverAppears) Stop(pid int) error              { s.stopped = true; return nil }
func (s *mountNeverAppears) Unmount(string, string) error    { return nil }
func (s *mountNeverAppears) MountFailureHint(pid int) string { return "provider_permission_denied" }

func TestMountReadinessFailureCarriesSafeProviderCategory(t *testing.T) {
	e, f, _ := mountFixture(t)
	runner := &mountNeverAppears{observer: f}
	e.run = runner
	_, err := e.Start("cloud")
	if err == nil || err.Error() != "FUSE readiness/mount identity not observed (provider_permission_denied)" {
		t.Fatalf("unexpected: %v", err)
	}
	if !runner.stopped {
		t.Fatal("unready child was not stopped")
	}
}
