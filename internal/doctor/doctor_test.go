package doctor

import (
	"context"
	"testing"
)

func TestMissingEvidenceNeverPasses(t *testing.T) {
	r := Reporter{}
	report := r.Run(context.Background())
	if report.Qualification != "SOURCE_ONLY_DEVICE_NOT_ATTESTED" || len(report.Checks) != 10 {
		t.Fatal(report)
	}
	for _, c := range report.Checks {
		if c.Status == "PASS" {
			t.Fatal("missing evidence reported pass")
		}
	}
}
func TestInvalidProbeFails(t *testing.T) {
	r := Reporter{Probes: map[string]Probe{"runtime": func(context.Context) (string, string) { return "GREEN", "wrong token=secret" }}}
	report := r.Run(context.Background())
	if report.Checks[0].Status != "FAIL" {
		t.Fatal(report.Checks[0])
	}
}
