package lifecycle

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func recoveryProof(t *testing.T, e *Engine) string {
	t.Helper()
	p, err := e.StaleRecoveryPreview("cloud")
	if err != nil {
		t.Fatalf("preview: %v", err)
	}
	proof, ok := p["proof"].(string)
	if !ok || len(proof) != 64 {
		t.Fatal("proof missing")
	}
	return proof
}
func TestStaleRecoveryQuarantinesOnlyAndDisablesDesired(t *testing.T) {
	e, obs, runner := mountFixture(t)
	if _, err := e.Start("cloud"); err != nil {
		t.Fatal(err)
	}
	obs.tick++ // old recorded PID has been reused by an unrelated process
	obs.exe = "/vendor/bin/mtk_agpsd"
	obs.mounted = false
	proof := recoveryProof(t, e)
	if _, err := e.RecoverStaleRecord("cloud", proof, false); err == nil {
		t.Fatal("missing approval accepted")
	}
	got, err := e.RecoverStaleRecord("cloud", proof, true)
	if err != nil {
		t.Fatal(err)
	}
	if got["mount_started"] != false || got["recovered"] != true {
		t.Fatalf("incorrect receipt: %v", got)
	}
	if runner.starts != 1 || runner.stops != 0 || runner.unmounts != 0 {
		t.Fatalf("unsafe process side effect: %+v", runner)
	}
	desired, err := e.Desired("cloud")
	if err != nil || desired {
		t.Fatal("desired remains active", desired, err)
	}
	if _, err = os.Stat(e.recordFile("cloud")); !os.IsNotExist(err) {
		t.Fatal("stale primary record retained", err)
	}
	files, err := os.ReadDir(e.dir)
	if err != nil {
		t.Fatal(err)
	}
	archives := 0
	for _, f := range files {
		if strings.HasPrefix(f.Name(), "stale-ownership-cloud-") && strings.HasSuffix(f.Name(), ".json") {
			archives++
			info, err := f.Info()
			if err != nil || info.Mode().Perm() != 0600 {
				t.Fatal("unsafe archive permissions", err)
			}
		}
	}
	if archives != 1 {
		t.Fatalf("expected one private archive, got %d", archives)
	}
	s, err := e.Status("cloud")
	if err != nil || s.Observed != "STOPPED" {
		t.Fatal(s, err)
	}
	if _, err = e.RecoverStaleRecord("cloud", proof, true); err == nil {
		t.Fatal("replayed proof accepted")
	}
}
func TestStaleRecoveryRefusesOwnedAndForeignMount(t *testing.T) {
	e, obs, runner := mountFixture(t)
	if _, err := e.Start("cloud"); err != nil {
		t.Fatal(err)
	}
	if _, err := e.StaleRecoveryPreview("cloud"); err == nil {
		t.Fatal("live owner accepted")
	}
	obs.tick++
	obs.exe = "/vendor/bin/mtk_agpsd"
	if _, err := e.StaleRecoveryPreview("cloud"); err == nil {
		t.Fatal("mounted foreign filesystem accepted")
	}
	if runner.stops != 0 || runner.unmounts != 0 {
		t.Fatal("unexpected stop")
	}
}
func TestStaleRecoveryProofRejectsIdentityRestorationAndChangedRecord(t *testing.T) {
	e, obs, runner := mountFixture(t)
	if _, err := e.Start("cloud"); err != nil {
		t.Fatal(err)
	}
	originalTick := obs.tick
	originalExe := obs.exe
	obs.tick++
	obs.mounted = false
	proof := recoveryProof(t, e)
	obs.tick = originalTick
	obs.exe = originalExe
	if _, err := e.RecoverStaleRecord("cloud", proof, true); err == nil {
		t.Fatal("restored identity accepted")
	}
	obs.tick++
	proof = recoveryProof(t, e)
	record := e.recordFile("cloud")
	b, err := os.ReadFile(record)
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(record, append(b, ' '), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err = e.RecoverStaleRecord("cloud", proof, true); err == nil {
		t.Fatal("changed record accepted")
	}
	if runner.stops != 0 || runner.unmounts != 0 {
		t.Fatal("mutation on proof failure")
	}
	if _, err = os.Stat(filepath.Join(e.dir, "process-cloud.json")); err != nil {
		t.Fatal("record improperly deleted")
	}
}
