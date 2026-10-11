package policy

import (
	"skybind/internal/mounts/config"
	"testing"
	"time"
)

func TestFailClosedUnknownResources(t *testing.T) {
	now := time.Now()
	m := config.Mount{NetworkMode: "unmetered", ChargingOnly: true, MinBatteryPercent: 20, MinCacheFreeBytes: 1}
	if Evaluate(m, Facts{}, now).Allowed {
		t.Fatal("unknown resources permitted")
	}
	falseValue := false
	trueValue := true
	battery := 30
	free := int64(10)
	f := Facts{Network: WiFi, Metered: &falseValue, Charging: &trueValue, Battery: &battery, CacheFreeBytes: &free}
	if !Evaluate(m, f, now).Allowed {
		t.Fatal("known adequate resources rejected")
	}
	f.Metered = &trueValue
	if Evaluate(m, f, now).Allowed {
		t.Fatal("metered connection passed unmetered gate")
	}
}
func TestOfflineAllowed(t *testing.T) {
	m := config.Mount{NetworkMode: "offline-allowed"}
	if !Evaluate(m, Facts{Network: Unknown}, time.Now()).Allowed {
		t.Fatal("explicit offline access denied")
	}
}
func TestProfilesAreCopies(t *testing.T) {
	p := Profiles()
	p[0].MaxBytes = 1
	if Profiles()[0].MaxBytes == 1 {
		t.Fatal("profile mutated")
	}
}
func TestSettleTimesFailClosed(t *testing.T) {
	m := config.Mount{NetworkMode: "offline-allowed", BootSettleSeconds: 10, NetworkSettleSeconds: 5}
	if Evaluate(m, Facts{}, time.Now()).Allowed {
		t.Fatal("accepted unknown boot clock")
	}
}
