package brokeridentity

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"testing"

	"skybind/internal/brokeripc"
)

type fakeProc struct {
	tick    int
	uid     uint32
	missing bool
	count   int
	change  bool
}

func (p *fakeProc) Read(pid int32, name string) ([]byte, error) {
	p.count++
	if p.missing {
		return nil, errors.New("no_proc")
	}
	if name == "status" {
		return []byte(fmt.Sprintf("Name:\tapp\nUid:\t%d\t%d\t%d\t%d\n", p.uid, p.uid, p.uid, p.uid)), nil
	}
	if p.change && p.count > 2 {
		p.tick++
	}
	// /proc stat has PID, comm, state, fields 4..21 (18 values), then starttime.
	return []byte(fmt.Sprintf("%d (unsafe ) name) S %s %d 0 0", pid, strings.TrimSpace(strings.Repeat("0 ", 18)), p.tick)), nil
}

type attestor struct {
	reject bool
	calls  int
	last   PackagePin
}

func (a *attestor) Verify(_ context.Context, _ uint32, p PackagePin) error {
	a.calls++
	a.last = p
	if a.reject {
		return errors.New("invalid_platform_attestation")
	}
	return nil
}
func TestProcessAndPackagePinnedIdentity(t *testing.T) {
	cert := strings.Repeat("a", 64)
	p := &fakeProc{uid: 10124, tick: 12345}
	a := &attestor{}
	v := &AndroidVerifier{Pins: map[uint32]PackagePin{10124: {Name: "io.example.bkx", CertSHA256: cert}}, Proc: p, Packages: a}
	peer := brokeripc.KernelPeer{UID: 10124, GID: 10124, PID: 199}
	identity, e := v.VerifyPeer(peer)
	if e != nil || identity.UID != peer.UID || len(identity.ProcessKey) != 64 || a.calls != 1 {
		t.Fatal(identity, e)
	}
	again, e := v.VerifyPeer(peer)
	if e != nil || again != identity {
		t.Fatal("unstable identity", e)
	}
	p.tick++
	newID, e := v.VerifyPeer(peer)
	if e != nil || newID.ProcessKey == identity.ProcessKey {
		t.Fatal("PID incarnation not bound", e)
	}
}
func TestMissingAttestorAndUntrustedPeerFailClosed(t *testing.T) {
	cert := strings.Repeat("0", 64)
	p := &fakeProc{uid: 10244, tick: 99}
	a := &attestor{}
	good := brokeripc.KernelPeer{UID: 10244, GID: 10244, PID: 451}
	makeV := func() *AndroidVerifier {
		return &AndroidVerifier{Pins: map[uint32]PackagePin{10244: {Name: "io.example.client", CertSHA256: cert}}, Proc: p, Packages: a}
	}
	cases := []struct {
		name   string
		change func(*AndroidVerifier, *brokeripc.KernelPeer)
	}{
		{"missing verifier", func(v *AndroidVerifier, _ *brokeripc.KernelPeer) { v.Packages = nil }},
		{"wrong uid", func(_ *AndroidVerifier, p *brokeripc.KernelPeer) { p.UID++ }},
		{"root", func(_ *AndroidVerifier, p *brokeripc.KernelPeer) { p.UID = 0 }},
		{"wrong process uid", func(_ *AndroidVerifier, p *brokeripc.KernelPeer) { p.GID = 0 }},
		{"no pin", func(v *AndroidVerifier, _ *brokeripc.KernelPeer) { v.Pins = nil }},
		{"bad cert", func(v *AndroidVerifier, _ *brokeripc.KernelPeer) {
			v.Pins[10244] = PackagePin{Name: "io.example.client", CertSHA256: "bad"}
		}},
		{"missing proc", func(v *AndroidVerifier, _ *brokeripc.KernelPeer) { v.Proc = nil }},
		{"invalid pid", func(_ *AndroidVerifier, p *brokeripc.KernelPeer) { p.PID = 0 }},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			v := makeV()
			peer := good
			tc.change(v, &peer)
			if _, e := v.VerifyPeer(peer); e == nil {
				t.Fatal("authorized without mandatory evidence")
			}
		})
	}
	a.reject = true
	if _, e := makeV().VerifyPeer(good); e == nil {
		t.Fatal("attestor denial ignored")
	}
	a.reject = false
	p.change = true
	if _, e := makeV().VerifyPeer(good); e == nil {
		t.Fatal("changed starttime accepted")
	}
}
func TestStrictKernelProcessParsing(t *testing.T) {
	if _, e := parseStartTicks([]byte("123 (name) S 0 0"), 123); e == nil {
		t.Fatal("short stat")
	}
	if _, e := parseStartTicks([]byte("122 (name) S "+strings.Repeat("0 ", 18)+"12"), 123); e == nil {
		t.Fatal("wrong pid")
	}
	for _, status := range []string{"Uid: 1000 1001 1000 1000", "Uid: potato", "Name: process"} {
		if _, e := parseStatusUID([]byte(status)); e == nil {
			t.Fatal("accepted status", status)
		}
	}
}
