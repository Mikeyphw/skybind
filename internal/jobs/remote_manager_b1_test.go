package jobs

import (
	"context"
	"os"
	"path/filepath"
	"skybind/internal/mounts/policy"
	"testing"
	"time"
)

type b1Runner struct {
	entered chan Job
	gate    chan struct{}
}

func (r b1Runner) Execute(ctx context.Context, j Job) error {
	r.entered <- j
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-r.gate:
		return nil
	}
}
func TestB1EphemeralCopyAndCheckReplay(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "jobs")
	if e := os.Mkdir(dir, 0700); e != nil {
		t.Fatal(e)
	}
	runner := b1Runner{entered: make(chan Job, 2), gate: make(chan struct{})}
	s, e := Open(dir, runner, func() policy.Facts { return policy.Facts{Network: policy.WiFi} })
	if e != nil {
		t.Fatal(e)
	}
	fp := "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
	spec := RemoteTransfer{Kind: "copy", Source: "alpha:photos", Destination: "beta:archive"}
	preview, e := s.RemoteTransferPreview(spec, fp)
	if e != nil {
		t.Fatal(e)
	}
	p := proof(t, preview)
	if _, e = s.RemoteTransferStart(spec, "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", p); e == nil {
		t.Fatal("config drift allowed")
	}
	// Proof is single-spend and invalidated by mismatched fingerprint.
	preview, e = s.RemoteTransferPreview(spec, fp)
	if e != nil {
		t.Fatal(e)
	}
	run, e := s.RemoteTransferStart(spec, fp, proof(t, preview))
	if e != nil {
		t.Fatal(e)
	}
	j := <-runner.entered
	if !j.IgnoreExisting || j.Kind != "copy" || j.IntervalSeconds != 0 {
		t.Fatalf("unsafe transient job %+v", j)
	}
	if _, e = s.RunStatus(run.ID); e != nil {
		t.Fatal(e)
	}
	if _, e = s.Cancel(run.ID); e != nil {
		t.Fatal(e)
	}
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		v, _ := s.RunStatus(run.ID)
		if v.State == "CANCELLED" {
			break
		}
		time.Sleep(time.Millisecond * 5)
	}
	restarted, e := Open(dir, runner, func() policy.Facts { return policy.Facts{Network: policy.WiFi} })
	if e != nil {
		t.Fatal(e)
	}
	v, e := restarted.RunStatus(run.ID)
	if e != nil || v.State != "CANCELLED" {
		t.Fatal(v, e)
	}
	snap, e := restarted.Snapshot()
	if e != nil {
		t.Fatal(e)
	}
	_ = snap
	preview, e = s.RemoteTransferPreview(RemoteTransfer{Kind: "check", Source: "alpha:a", Destination: "beta:b"}, fp)
	if e != nil {
		t.Fatal(e)
	}
	second, e := s.RemoteTransferStart(RemoteTransfer{Kind: "check", Source: "alpha:a", Destination: "beta:b"}, fp, proof(t, preview))
	if e != nil {
		t.Fatal(e)
	}
	checked := <-runner.entered
	if checked.IgnoreExisting || checked.Kind != "check" {
		t.Fatal("read only check incorrect", checked)
	}
	if _, e = s.Cancel(second.ID); e != nil {
		t.Fatal(e)
	}
	for time.Now().Before(time.Now().Add(2 * time.Second)) {
		v, _ := s.RunStatus(second.ID)
		if v.State == "CANCELLED" {
			break
		}
		time.Sleep(time.Millisecond * 5)
	}
	v, _ = s.RunStatus(second.ID)
	if v.State != "CANCELLED" {
		t.Fatalf("second run still active: %s", v.State)
	}
}
func TestB1RejectDestructiveAndUnsafeEndpoint(t *testing.T) {
	bad := []RemoteTransfer{
		{Kind: "sync", Source: "alpha:a", Destination: "beta:b"},
		{Kind: "move", Source: "alpha:a", Destination: "beta:b"},
		{Kind: "copy", Source: "alpha:", Destination: "beta:b"},
		{Kind: "copy", Source: "alpha:a", Destination: "beta:"},
		{Kind: "copy", Source: "alpha:a", Destination: "alpha:a/subfolder"},
		{Kind: "copy", Source: "alpha:a/subfolder", Destination: "alpha:a"},
		{Kind: "copy", Source: "alpha:../private", Destination: "beta:b"},
		{Kind: "copy", Source: "/data/adb/skybind", Destination: "beta:b"},
		{Kind: "copy", Source: "alpha:a", Destination: "alpha:a"},
	}
	for _, v := range bad {
		if e := validRemoteTransfer(v); e == nil {
			t.Errorf("accepted unsafe %+v", v)
		}
	}
}
