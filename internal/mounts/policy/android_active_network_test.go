package policy

import "testing"

func TestAndroidValidatedDefaultNetworkFallback(t *testing.T) {
	cases := []struct {
		name    string
		raw     string
		want    Network
		metered *bool
	}{
		{"validated wifi", `Active default network: 101
Current Networks:
 NetworkAgentInfo{network{100} nc{[ Transports: CELLULAR Capabilities: INTERNET&VALIDATED&NOT_VPN ]}}
 NetworkAgentInfo{network{101} nc{[ Transports: WIFI Capabilities: INTERNET&VALIDATED&NOT_VPN&NOT_METERED ]}}
`, WiFi, boolPtr(false)},
		{"validated cellular", `Active default network: 102
Current Networks:
 NetworkAgentInfo{network{102} nc{[ Transports: CELLULAR Capabilities: INTERNET&VALIDATED&NOT_VPN ]}}
`, Cellular, boolPtr(true)},
		{"no active", `Active default network: none
 NetworkAgentInfo{network{101} nc{[ Transports: WIFI Capabilities: INTERNET&VALIDATED&NOT_VPN ]}}`, Unknown, nil},
		{"unvalidated", `Active default network: 101
 NetworkAgentInfo{network{101} nc{[ Transports: WIFI Capabilities: INTERNET&NOT_VPN ]}}`, Unknown, nil},
		{"vpn", `Active default network: 101
 NetworkAgentInfo{network{101} nc{[ Transports: VPN Capabilities: INTERNET&VALIDATED ]}}`, Unknown, nil},
		{"mixed transport", `Active default network: 101
 NetworkAgentInfo{network{101} nc{[ Transports: WIFI|CELLULAR Capabilities: INTERNET&VALIDATED&NOT_VPN ]}}`, Unknown, nil},
		{"duplicate agents", `Active default network: 101
 NetworkAgentInfo{network{101} nc{[ Transports: WIFI Capabilities: INTERNET&VALIDATED&NOT_VPN ]}}
 NetworkAgentInfo{network{101} nc{[ Transports: WIFI Capabilities: INTERNET&VALIDATED&NOT_VPN ]}}`, Unknown, nil},
		{"wrong active agent", `Active default network: 201
 NetworkAgentInfo{network{101} nc{[ Transports: WIFI Capabilities: INTERNET&VALIDATED&NOT_VPN ]}}`, Unknown, nil},
		{"ambiguous active", `Active default network: 101
Active default network: 102
 NetworkAgentInfo{network{101} nc{[ Transports: WIFI Capabilities: INTERNET&VALIDATED&NOT_VPN ]}}`, Unknown, nil},
		{"no capabilities", `Active default network: 101
 NetworkAgentInfo{network{101} nc{[ Transports: WIFI LinkUpBandwidth: 100 ]}}`, Unknown, nil},
		{"capability spoof in another agent", `Active default network: 101
 NetworkAgentInfo{network{101} nc{[ Transports: WIFI Capabilities: INTERNET ]}}
 NetworkAgentInfo{network{102} nc{[ Transports: WIFI Capabilities: INTERNET&NOT_VPN&VALIDATED ]}}`, Unknown, nil},
		{"large dump rejected", string(make([]byte, (1<<20)+1)), Unknown, nil},
		{"full modern network dump", `Active default network: 101
Current Networks:
 NetworkAgentInfo{network{101} handle{432902426637} ni{WIFI CONNECTED extra: } Score(60) lp{{InterfaceName: wlan0}} nc{[ Transports: WIFI Capabilities: NOT_METERED&INTERNET&NOT_RESTRICTED&TRUSTED&NOT_VPN&VALIDATED&NOT_ROAMING LinkUpBandwidth>=12000Kbps LinkDnBandwidth>=30000Kbps ]}}`, WiFi, boolPtr(false)},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, meter := parseValidatedActiveNetwork([]byte(tc.raw))
			if got != tc.want || (meter == nil) != (tc.metered == nil) {
				t.Fatalf("network=%s metered=%v; want %s, %v", got, meter, tc.want, tc.metered)
			}
			if meter != nil && *meter != *tc.metered {
				t.Fatalf("metered=%v; want %v", *meter, *tc.metered)
			}
		})
	}
}
