package lifecycle

import (
	"os"
	"skybind/internal/paths"
	"testing"
	"time"
)

// lateMountObserver intentionally withholds the FUSE mount until after the
// former 20-poll limit; the provider and process identity stay stable.
type lateMountObserver struct {
	*fakeObserver
	pending int
	checks  int
}

func (o *lateMountObserver) Mount(point string) (MountObservation, bool, error) {
	if o.fakeObserver.mounted {
		o.checks++
		if o.checks <= o.pending {
			return MountObservation{}, false, nil
		}
	}
	return o.fakeObserver.Mount(point)
}

func TestMountStartupAfterOldTwentyPollLimit(t *testing.T) {
	e, f, runner := mountFixture(t)
	late := &lateMountObserver{fakeObserver: f, pending: 24}
	e.obs = late
	e.mountReadyTimeout = 200 * time.Millisecond
	e.mountReadyPoll = 1 * time.Millisecond
	state, err := e.Start("cloud")
	if err != nil || state.Observed != "RUNNING" {
		t.Fatalf("valid late FUSE start rejected: state=%+v err=%v", state, err)
	}
	if late.checks <= 20 || runner.stops != 0 {
		t.Fatalf("old 20-poll limit still active or child stopped: checks=%d stops=%d", late.checks, runner.stops)
	}
}

type childGoneObserver struct {
	*fakeObserver
	checks int
}

func (o *childGoneObserver) Identity(pid int) (uint64, string, error) {
	o.checks++
	if o.checks > 3 {
		return 0, "", os.ErrNotExist
	}
	return o.fakeObserver.Identity(pid)
}

func TestMountStartupNeverSignalsUnverifiableChild(t *testing.T) {
	e, f, runner := mountFixture(t)
	e.obs = &childGoneObserver{fakeObserver: f}
	e.mountReadyTimeout = 250 * time.Millisecond
	e.mountReadyPoll = time.Millisecond
	// A child exists, but the FUSE mount never arrives before the PID is gone.
	runnerStart := &mountNeverAppears{observer: f}
	e.run = runnerStart
	if _, err := e.Start("cloud"); err == nil {
		t.Fatal("accepted mount after original process became unobservable")
	}
	if runnerStart.stopped {
		t.Fatal("signaled unverifiable child PID")
	}
	_ = runner
}

func TestCanonicalMountReadinessBudget(t *testing.T) {
	e, _, _ := mountFixture(t)
	if e.mountReadyTimeout != 10*time.Second || e.mountReadyPoll != 100*time.Millisecond {
		t.Fatalf("unexpected production FUSE readiness budget: %s %s", e.mountReadyTimeout, e.mountReadyPoll)
	}
	if paths.Engine == "" {
		t.Fatal("missing canonical engine")
	}
}
