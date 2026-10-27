package featuregateway

import (
	"context"
	"encoding/json"
	"fmt"
	"skybind/internal/brokeridentity"
	"skybind/internal/brokeripc"
	"skybind/internal/protocol"
	"strconv"
	"strings"
	"testing"
)

func samplePolicy() Policy {
	p := Policy{Schema: Schema, ExplicitlyEnabled: true, Operations: []string{"mount.status", "mount.health"}, MountNames: []string{"safeMount"}}
	p.BKX.Package = "com.mikeyphw.bkx.android"
	p.BKX.UID = 11091
	p.BKX.CertSHA256 = strings.Repeat("a", 64)
	p.BKX.SELinuxContext = "u:r:untrusted_app:s0:c100,c200"
	return p
}
func policyJSON(p Policy) []byte { b, _ := json.Marshal(p); return b }
func TestAPI04PolicyFailClosed(t *testing.T) {
	base := samplePolicy()
	if e := base.Validate(); e != nil {
		t.Fatal(e)
	}
	cases := []struct {
		name   string
		mutate func(*Policy)
	}{
		{"disabled", func(p *Policy) { p.ExplicitlyEnabled = false }},
		{"no UID", func(p *Policy) { p.BKX.UID = 0 }},
		{"wrong package", func(p *Policy) { p.BKX.Package = "com.evil.app" }},
		{"wrong certificate", func(p *Policy) { p.BKX.CertSHA256 = "signer-garbage" }},
		{"wrong SELinux", func(p *Policy) { p.BKX.SELinuxContext = "u:r:untrusted_app:s0\n" }},
		{"empty scope", func(p *Policy) { p.Operations = nil }},
		{"arbitrary shell", func(p *Policy) { p.Operations = []string{"exec.shell"} }},
		{"mount mutation", func(p *Policy) { p.Operations = []string{"mount.start"} }},
		{"namespace mutation", func(p *Policy) { p.Operations = []string{"namespace.apply"} }},
		{"preview prohibited", func(p *Policy) { p.Operations = []string{"namespace.preview"} }},
		{"duplicate operation", func(p *Policy) { p.Operations = []string{"mount.status", "mount.status"} }},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			p := base
			p.Operations = append([]string(nil), base.Operations...)
			tc.mutate(&p)
			if p.Validate() == nil {
				t.Fatal("accepted unauthorized policy")
			}
		})
	}
	samples := [][]byte{
		[]byte(`{"schema":"` + Schema + `","schema":"` + Schema + `"}`),
		[]byte(`{"bkx":{"uid":11091,"uid":11092}}`),
		append(policyJSON(base), []byte(`{}`)...),
		[]byte(`[]`),
		[]byte(`{"schema":1}`),
		make([]byte, maxPolicyBytes+1),
	}
	for i, b := range samples {
		if _, e := DecodePolicy(b); e == nil {
			t.Fatalf("accepted malformed policy %d", i)
		}
	}
	if _, e := DecodePolicy(policyJSON(base)); e != nil {
		t.Fatal(e)
	}
	var raw map[string]any
	_ = json.Unmarshal(policyJSON(base), &raw)
	raw["unknown"] = "x"
	b, _ := json.Marshal(raw)
	if _, e := DecodePolicy(b); e == nil {
		t.Fatal("unknown policy accepted")
	}
}

type procFixture struct {
	pid   int32
	label string
	uid   uint32
	start uint64
}

func (p procFixture) Read(pid int32, filename string) ([]byte, error) {
	if pid != p.pid {
		return nil, fmt.Errorf("missing process")
	}
	switch filename {
	case "stat":
		parts := make([]string, 20)
		for i := range parts {
			parts[i] = "0"
		}
		parts[0] = "S"
		parts[19] = strconv.FormatUint(p.start, 10)
		return []byte(fmt.Sprintf("%d (com.mikeyphw.bkx.android) %s\n", pid, strings.Join(parts, " "))), nil
	case "status":
		return []byte(fmt.Sprintf("Name:\tbkx\nUid:\t%d\t%d\t%d\t%d\n", p.uid, p.uid, p.uid, p.uid)), nil
	case "attr/current":
		return []byte(p.label + "\n"), nil
	}
	return nil, fmt.Errorf("unknown proc file")
}

type pmFixture struct{ ok bool }

func (p pmFixture) LookupInstalled(ctx context.Context, uid uint32, name string) (brokeridentity.PlatformPackageRecord, error) {
	if !p.ok {
		return brokeridentity.PlatformPackageRecord{}, fmt.Errorf("not trusted")
	}
	return brokeridentity.PlatformPackageRecord{UID: uid, PackagesForUID: []string{name}, InstalledPackage: name, APKContentsSigners: [][]byte{make([]byte, 128)}, IsInstalledForUser: true}, nil
}
func TestAPI04MissingIdentityAuthority(t *testing.T) {
	if _, e := NewGuard(samplePolicy(), Dependencies{}); e == nil {
		t.Fatal("accepted missing PM/proc authority")
	}
}
func TestAPI04GuardDeniesSpoofingAndMutations(t *testing.T) {
	p := samplePolicy()
	// The PM signature has a real SHA256 digest; update operator policy pin.
	// sha256(128 zero bytes) is fixed and independent of a client's JSON.
	p.BKX.CertSHA256 = "38723a2e5e8a17aa7950dc008209944e898f69a7bd10a23c839d341e935fd5ca"
	deps := Dependencies{Packages: pmFixture{ok: true}, Proc: procFixture{pid: 10101, uid: p.BKX.UID, label: p.BKX.SELinuxContext, start: 123}}
	g, e := NewGuard(p, deps)
	if e != nil {
		t.Fatal(e)
	}
	peer := brokeripc.KernelPeer{UID: p.BKX.UID, GID: p.BKX.UID, PID: 10101}
	call := func(operation string) []byte {
		return []byte(fmt.Sprintf(`{"api_version":1,"request_id":"request-42","operation":%q,"arguments":{"name":"safeMount"}}`, operation))
	}
	req, identity, e := g.Prepare(peer, call("mount.status"))
	if e != nil {
		t.Fatal(e)
	}
	if req.Operation != "feature.execute" || req.Class != protocol.Query || req.RequestID != "request-42" || identity.ProcessKey == "" {
		t.Fatalf("bad authorization receipt: %+v / %+v", req, identity)
	}
	for _, op := range []string{"mount.start", "namespace.apply", "operation.events", "rclone.lsjson", "mount.start.preview"} {
		if _, _, e := g.Prepare(peer, call(op)); e == nil {
			t.Fatal("accepted out-of-scope operation", op)
		}
	}
	for _, spoof := range []brokeripc.KernelPeer{{UID: 0, GID: 0, PID: 10101}, {UID: p.BKX.UID + 1, GID: p.BKX.UID + 1, PID: 10101}, {UID: p.BKX.UID, GID: 0, PID: 10101}, {UID: p.BKX.UID, GID: p.BKX.UID, PID: 99}} {
		if _, _, e := g.Prepare(spoof, call("mount.status")); e == nil {
			t.Fatal("accepted spoofed peer", spoof)
		}
	}
	for _, bad := range [][]byte{nil, []byte(`{"api_version":1,"request_id":"a","operation":"mount.status","arguments":{},"arguments":{}}`), []byte(`{"api_version":1,"request_id":"a","operation":"mount.status","arguments":{"proof":"a","proof":"b"}}`)} {
		if _, _, e := g.Prepare(peer, bad); e == nil {
			t.Fatal("accepted invalid call")
		}
	}
	for _, raw := range [][]byte{
		[]byte(`{"api_version":1,"request_id":"a","operation":"mount.status","arguments":{"name":"otherMount"}}`),
		[]byte(`{"api_version":1,"request_id":"a","operation":"mount.status","arguments":{"name":"safeMount","extra":"x"}}`),
		[]byte(`{"api_version":1,"request_id":"a","operation":"mount.status","arguments":{}}`),
	} {
		if _, _, e := g.Prepare(peer, raw); e == nil {
			t.Fatal("accepted foreign/unscoped mount request")
		}
	}
	g2, _ := NewGuard(p, Dependencies{Packages: pmFixture{ok: false}, Proc: deps.Proc})
	if _, _, e := g2.Prepare(peer, call("mount.status")); e == nil {
		t.Fatal("accepted rejected platform certificate")
	}
}
