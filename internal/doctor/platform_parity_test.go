package doctor

import (
	"context"
	"testing"
)

func TestDoctorNeverClaimsDeviceQualification(t *testing.T) {
	got := Canonical().Run(context.Background())
	if got.Qualification != "SOURCE_ONLY_DEVICE_NOT_ATTESTED" || len(got.Checks) != 10 {
		t.Fatal(got)
	}
	for _, c := range got.Checks {
		if c.Reason == "not_inspected" {
			t.Fatalf("placeholder probe remains: %s", c.ID)
		}
	}
}
