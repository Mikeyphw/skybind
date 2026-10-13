package lifecycle

import (
	"context"
	"errors"
	"skybind/internal/mounts/writeback"
	"testing"
)

func wd(state string) writeback.Snapshot {
	return writeback.Snapshot{State: state, Reason: "test", Mount: "cloud"}
}
func TestSafeStopWritebackFailClosed(t *testing.T) {
	for _, tc := range []struct {
		label  string
		status string
		err    error
		reason string
	}{
		{"unknown", "unknown", nil, "writeback_unavailable"},
		{"failed", "errored", nil, "writeback_errors"},
		{"request_error", "idle", errors.New("RC failed"), "writeback_unavailable"},
	} {
		t.Run(tc.label, func(t *testing.T) {
			e, _, run := mountFixture(t)
			if _, err := e.Start("cloud"); err != nil {
				t.Fatal(err)
			}
			e.ConfigureWriteback(func(context.Context, string) (writeback.Snapshot, error) { return wd(tc.status), tc.err })
			if _, err := e.Stop("cloud"); err == nil || err.Error() != tc.reason {
				t.Fatalf("err %v", err)
			}
			if run.unmounts != 0 || run.stops != 0 {
				t.Fatal("unsafe detached despite pending/unknown writes")
			}
			desired, _ := e.Desired("cloud")
			if !desired {
				t.Fatal("desired changed on refusal")
			}
		})
	}
}
func TestSafeStopAndRestartAfterDrain(t *testing.T) {
	e, _, run := mountFixture(t)
	if _, err := e.Start("cloud"); err != nil {
		t.Fatal(err)
	}
	calls := 0
	e.ConfigureWriteback(func(context.Context, string) (writeback.Snapshot, error) {
		calls++
		if calls == 1 {
			return writeback.Snapshot{State: "busy", Queued: 1}, nil
		}
		return wd("idle"), nil
	})
	if _, err := e.Stop("cloud"); err != nil {
		t.Fatal(err)
	}
	if calls < 2 || run.unmounts != 1 {
		t.Fatalf("calls=%d unmount=%d", calls, run.unmounts)
	}
	if _, err := e.Start("cloud"); err != nil {
		t.Fatal(err)
	}
	if _, err := e.Restart("cloud"); err != nil {
		t.Fatal(err)
	}
	if run.unmounts != 2 {
		t.Fatal("restart not guarded")
	}
}
func TestWritebackContextCancellationRefusesDetach(t *testing.T) {
	e, _, r := mountFixture(t)
	_, err := e.Start("cloud")
	if err != nil {
		t.Fatal(err)
	}
	e.ConfigureWriteback(func(context.Context, string) (writeback.Snapshot, error) {
		return writeback.Snapshot{State: "busy", Queued: 1}, nil
	})
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err = e.StopContext(ctx, "cloud"); err == nil || err.Error() != "writeback_cancelled" {
		t.Fatal(err)
	}
	if r.unmounts != 0 {
		t.Fatal("cancelled detach")
	}
}
func TestMissingProductionWritebackHookRefusesDetach(t *testing.T) {
	e, _, r := mountFixture(t)
	_, err := e.Start("cloud")
	if err != nil {
		t.Fatal(err)
	}
	e.ConfigureRC(func(string) ([]string, error) { return nil, nil }, func(string) {})
	if _, err = e.Stop("cloud"); err == nil || err.Error() != "writeback_unavailable" {
		t.Fatal(err)
	}
	if r.unmounts != 0 {
		t.Fatal("no probe but unmounted")
	}
}
