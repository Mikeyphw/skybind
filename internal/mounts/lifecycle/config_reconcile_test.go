package lifecycle

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"skybind/internal/mounts/config"
)

func transactionCandidate(t *testing.T, e *Engine, edit func(*config.Registry)) ([]byte, string) {
	t.Helper()
	snapshot, err := e.store.Snapshot()
	if err != nil {
		t.Fatal(err)
	}
	edit(&snapshot)
	raw, err := json.Marshal(snapshot)
	if err != nil {
		t.Fatal(err)
	}
	preview, err := e.store.Preview(raw)
	if err != nil {
		t.Fatal(err)
	}
	return raw, preview.Token
}

func TestConfigEditQuiescesOldIdentityBeforePublication(t *testing.T) {
	e, _, runner := mountFixture(t)
	if _, err := e.Start("cloud"); err != nil {
		t.Fatal(err)
	}
	raw, proof := transactionCandidate(t, e, func(r *config.Registry) {
		r.Mounts[0].Remote = "next:/"
		r.Mounts[0].Mountpoint = "/mnt/new-cloud"
	})
	committed, err := e.ApplyConfig(raw, proof)
	if err != nil {
		t.Fatal(err)
	}
	if committed.Revision != 2 || runner.starts != 2 || runner.stops != 1 || runner.unmounts != 1 {
		t.Fatalf("old lifecycle not reconciled, revision=%d starts=%d stops=%d unmounts=%d", committed.Revision, runner.starts, runner.stops, runner.unmounts)
	}
	data, err := os.ReadFile(e.recordFile("cloud"))
	if err != nil {
		t.Fatal(err)
	}
	var record Ownership
	if err := json.Unmarshal(data, &record); err != nil || record.Mountpoint != "/mnt/new-cloud" {
		t.Fatalf("new ownership not recorded: %+v %v", record, err)
	}
	// Previous-known-good stays available as a guarded rollback target.
	rollback, err := e.store.RollbackPreview()
	if err != nil {
		t.Fatal(err)
	}
	restored, err := e.RollbackConfig(rollback.Token)
	if err != nil || restored.Mounts[0].Mountpoint != "/mnt/cloud" || runner.stops != 2 || runner.starts != 3 {
		t.Fatalf("rollback did not reconcile process identity: %+v %v", restored, err)
	}
}

func TestDeleteOwnedMountCannotOrphanProcess(t *testing.T) {
	e, _, runner := mountFixture(t)
	if _, err := e.Start("cloud"); err != nil {
		t.Fatal(err)
	}
	raw, proof := transactionCandidate(t, e, func(r *config.Registry) { r.Mounts = []config.Mount{} })
	committed, err := e.ApplyConfig(raw, proof)
	if err != nil || len(committed.Mounts) != 0 {
		t.Fatalf("delete: %+v %v", committed, err)
	}
	if runner.stops != 1 || runner.unmounts != 1 {
		t.Fatal("deleted mount process left running")
	}
	if _, err := os.Stat(e.recordFile("cloud")); !os.IsNotExist(err) {
		t.Fatalf("ownership record not cleaned: %v", err)
	}
	wanted, err := e.Desired("cloud")
	if err != nil || wanted {
		t.Fatal("deleted desired state retained")
	}
}

func TestConfigPolicyOnlyDoesNotRestart(t *testing.T) {
	e, _, runner := mountFixture(t)
	if _, err := e.Start("cloud"); err != nil {
		t.Fatal(err)
	}
	raw, proof := transactionCandidate(t, e, func(r *config.Registry) { r.Mounts[0].LogLevel = "INFO" })
	if _, err := e.ApplyConfig(raw, proof); err != nil {
		t.Fatal(err)
	}
	if runner.starts != 1 || runner.stops != 0 || runner.unmounts != 0 {
		t.Fatal("policy-only change interrupted healthy FUSE process")
	}
}

func TestConfigRejectsForeignProcessWithoutPublishing(t *testing.T) {
	e, observer, runner := mountFixture(t)
	if _, err := e.Start("cloud"); err != nil {
		t.Fatal(err)
	}
	raw, proof := transactionCandidate(t, e, func(r *config.Registry) { r.Mounts[0].Remote = "changed:/" })
	observer.tick++ // simulate PID reuse or untrusted process replacement
	if _, err := e.ApplyConfig(raw, proof); err == nil {
		t.Fatal("foreign identity accepted")
	}
	snapshot, err := e.store.Snapshot()
	if err != nil || snapshot.Revision != 1 || snapshot.Mounts[0].Remote != "example:/" {
		t.Fatalf("failed quiesce published new registry: %+v %v", snapshot, err)
	}
	if runner.stops != 0 || runner.unmounts != 0 {
		t.Fatal("foreign process or mount targeted")
	}
	if _, err := os.Stat(filepath.Join(e.storeDirectoryForTest(), config.PendingName)); err == nil {
		t.Fatal("pending transaction not cleared after rejected preparation")
	}
}

func (e *Engine) storeDirectoryForTest() string { return filepath.Join(filepath.Dir(e.dir), "config") }

func TestStopFailureKeepsDesiredState(t *testing.T) {
	e, observer, _ := mountFixture(t)
	if _, err := e.Start("cloud"); err != nil {
		t.Fatal(err)
	}
	observer.tick++
	if _, err := e.Stop("cloud"); err == nil {
		t.Fatal("foreign process accepted")
	}
	desired, err := e.Desired("cloud")
	if err != nil || !desired {
		t.Fatal("failed stop silently discarded desired state")
	}
}

func TestPublishedButRestartBlockedReportsAttention(t *testing.T) {
	e, _, _ := mountFixture(t)
	if _, err := e.Start("cloud"); err != nil {
		t.Fatal(err)
	}
	raw, proof := transactionCandidate(t, e, func(r *config.Registry) {
		r.Mounts[0].Remote = "next:/"
		r.Mounts[0].NetworkMode = "wifi" // fake resource facts do not qualify wifi
	})
	committed, err := e.ApplyConfig(raw, proof)
	if err == nil || !strings.Contains(err.Error(), "published") || committed.Revision != 2 {
		t.Fatalf("did not report partial commit: %+v %v", committed, err)
	}
	b, err := os.ReadFile(filepath.Join(e.dir, "config-attention-v1.json"))
	if err != nil || !strings.Contains(string(b), "revision") {
		t.Fatalf("no durable attention: %s %v", b, err)
	}
	wanted, err := e.Desired("cloud")
	if err != nil || !wanted {
		t.Fatal("restart intent lost")
	}
}

func TestFirstConfigPublicationCreatesPrivateDesiredDirectory(t *testing.T) {
	base := t.TempDir()
	cfgDir := filepath.Join(base, "config")
	if err := os.Mkdir(cfgDir, 0700); err != nil {
		t.Fatal(err)
	}
	store, err := config.Open(cfgDir)
	if err != nil {
		t.Fatal(err)
	}
	dir := filepath.Join(base, "desired") // intentionally absent
	observed := &fakeObserver{}
	engine := newEngine(store, dir, observed, &fakeRunner{f: observed}, fakeEnv{ready: true})
	candidate := config.Empty()
	candidate.Mounts = []config.Mount{{Name: "cloud", Remote: "example:/", Mountpoint: "/mnt/cloud", Enabled: true, NetworkMode: "offline-allowed"}}
	raw, _ := json.Marshal(candidate)
	preview, err := store.Preview(raw)
	if err != nil {
		t.Fatal(err)
	}
	published, err := engine.ApplyConfig(raw, preview.Token)
	if err != nil || published.Revision != 1 {
		t.Fatalf("initial publication: %+v %v", published, err)
	}
	st, err := os.Stat(dir)
	if err != nil || st.Mode().Perm() != 0700 {
		t.Fatalf("state dir not private: %v %v", st, err)
	}
}
