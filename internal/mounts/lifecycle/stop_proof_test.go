package lifecycle

import (
	"context"
	"skybind/internal/mounts/config"
	"testing"
)

func stopToken(t *testing.T, e *Engine) string {
	t.Helper()
	p, err := e.StopPreview("cloud")
	if err != nil {
		t.Fatal(err)
	}
	proof, ok := p["proof"].(string)
	if !ok || len(proof) != 64 {
		t.Fatalf("missing secure stop proof: %v", p)
	}
	return proof
}

func TestGuardedStopSingleUseNoBypass(t *testing.T) {
	e, _, runner := mountFixture(t)
	if _, err := e.Start("cloud"); err != nil {
		t.Fatal(err)
	}
	if _, err := e.StopGuardedContext(context.Background(), "cloud", "no-proof"); err == nil {
		t.Fatal("forged proof accepted")
	}
	if runner.stops != 0 {
		t.Fatal("forged proof killed process")
	}
	proof := stopToken(t, e)
	if _, err := e.StopGuardedContext(context.Background(), "cloud", proof); err != nil {
		t.Fatal(err)
	}
	if runner.stops != 1 || runner.unmounts != 1 {
		t.Fatalf("stop count=%d detach=%d", runner.stops, runner.unmounts)
	}
	if _, err := e.StopGuardedContext(context.Background(), "cloud", proof); err == nil {
		t.Fatal("replayed proof accepted")
	}
	if runner.stops != 1 {
		t.Fatal("proof replay triggered extra stop")
	}
}

func TestGuardedStopRejectsChangedOwnerIdentity(t *testing.T) {
	e, obs, runner := mountFixture(t)
	if _, err := e.Start("cloud"); err != nil {
		t.Fatal(err)
	}
	proof := stopToken(t, e)
	obs.tick++
	if _, err := e.StopGuardedContext(context.Background(), "cloud", proof); err == nil {
		t.Fatal("changed PID incarnation accepted")
	}
	if runner.stops != 0 || runner.unmounts != 0 {
		t.Fatal("PID identity drift caused side effect")
	}
}

func TestGuardedStopRejectsReplacedMountID(t *testing.T) {
	e, obs, runner := mountFixture(t)
	if _, err := e.Start("cloud"); err != nil {
		t.Fatal(err)
	}
	proof := stopToken(t, e)
	obs.mountID = "other-mount-id"
	if _, err := e.StopGuardedContext(context.Background(), "cloud", proof); err == nil {
		t.Fatal("replaced FUSE identity accepted")
	}
	if runner.stops != 0 || runner.unmounts != 0 {
		t.Fatal("replaced FUSE caused side effect")
	}
}

func TestGuardedStopRejectsStaleConfigRevision(t *testing.T) {
	e, _, runner := mountFixture(t)
	if _, err := e.Start("cloud"); err != nil {
		t.Fatal(err)
	}
	proof := stopToken(t, e)
	// Policy-only publication changes the registry revision but does not stop
	// or restart the running mount. Old stop approval must nevertheless fail.
	raw, candidateProof := transactionCandidate(t, e, func(r *config.Registry) { r.Mounts[0].LogLevel = "INFO" })
	if _, err := e.ApplyConfig(raw, candidateProof); err != nil {
		t.Fatal(err)
	}
	if runner.stops != 0 {
		t.Fatal("configuration edit unexpectedly stopped mount")
	}
	if _, err := e.StopGuardedContext(context.Background(), "cloud", proof); err == nil {
		t.Fatal("stale revision proof accepted")
	}
	if runner.stops != 0 || runner.unmounts != 0 {
		t.Fatal("stale proof triggered stop")
	}
}

func TestGuardedStopRequiresRunningOwnedMount(t *testing.T) {
	e, _, _ := mountFixture(t)
	if _, err := e.StopPreview("cloud"); err == nil {
		t.Fatal("issued stop proof for stopped mount")
	}
}
