package policy

import (
	"skybind/internal/mounts/config"
	"testing"
	"time"
)

func TestActiveNetworkMeteringIsIsolated(t *testing.T) {
	cases := []struct {
		name, body string
		want       *bool
	}{
		{"active wifi unmetered", `Active default network: 101
NetworkAgentInfo{ network{999} Capabilities: INTERNET&NOT_METERED }
NetworkAgentInfo{ network{101} Capabilities: INTERNET&NOT_METERED&VALIDATED }`, boolPtr(false)},
		{"active cellular metered", `Active default network: 102
NetworkAgentInfo{ network{101} Capabilities: INTERNET&NOT_METERED }
NetworkAgentInfo{ network{102} Capabilities: INTERNET&VALIDATED }`, boolPtr(true)},
		{"missing active", `NetworkAgentInfo{ network{101} Capabilities: NOT_METERED }`, nil},
		{"unmatched active", `Active default network: 102
NetworkAgentInfo{ network{101} Capabilities: NOT_METERED }`, nil},
		{"ambiguous active", `Active default network: 101
Active default network: 102
NetworkAgentInfo{ network{101} Capabilities: NOT_METERED }`, nil},
		{"duplicate agent", `Active default network: 101
NetworkAgentInfo{ network{101} Capabilities: NOT_METERED }
NetworkAgentInfo{ network{101} Capabilities: INTERNET }`, nil},
		{"incomplete capabilities", `Active default network: 101
NetworkAgentInfo{ network{101} Other: NOT_METERED }`, nil},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got := parseActiveMetered([]byte(c.body))
			if (got == nil) != (c.want == nil) {
				t.Fatalf("got %v want %v", got, c.want)
			}
			if got != nil && *got != *c.want {
				t.Fatal(*got, *c.want)
			}
		})
	}
}
func boolPtr(b bool) *bool { return &b }
func TestSettlingCannotBeFabricated(t *testing.T) {
	now := time.Now()
	m := config.Mount{NetworkMode: "unmetered", NetworkSettleSeconds: 120}
	f := Facts{Network: WiFi, Metered: boolPtr(false)}
	if Evaluate(m, f, now).Allowed {
		t.Fatal("missing real sample accepted")
	}
	f.NetworkAt = now.Add(-time.Second)
	if Evaluate(m, f, now).Allowed {
		t.Fatal("new network accepted before settle")
	}
	f.NetworkAt = now.Add(-121 * time.Second)
	if !Evaluate(m, f, now).Allowed {
		t.Fatal("stable proven network denied")
	}
	f.Metered = nil
	if Evaluate(m, f, now).Allowed {
		t.Fatal("unknown metering accepted")
	}
}
func TestAdvisoryBoundaries(t *testing.T) {
	if a := Recommend(0, 1<<40); a.Known {
		t.Fatal(a)
	}
	if a := Recommend(2<<30, 500<<20); !a.Known || a.Profile != "minimal" || a.SuggestedMaxBytes > 250<<20 {
		t.Fatal(a)
	}
	if a := Recommend(8<<30, 20<<30); !a.Known || a.Profile != "streaming" || a.SuggestedMaxBytes > 4<<30 {
		t.Fatal(a)
	}
	if a := Recommend(8<<30, 2<<30); !a.Known || a.SuggestedMaxBytes > 1<<30 {
		t.Fatal(a)
	}
}
