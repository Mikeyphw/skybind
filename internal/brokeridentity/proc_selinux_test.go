package brokeridentity

import (
	"skybind/internal/brokeripc"
	"strings"
	"testing"
)

func TestProcSELinuxLabelOnlyTerminalBytes(t *testing.T) {
	base := "u:r:untrusted_app:s0:c79,c257,c512,c768"
	good := []string{base, base + "\n", base + "\x00", base + "\x00\n", base + "\n\x00"}
	for _, s := range good {
		got, err := procSELinuxLabel([]byte(s))
		if err != nil || got != base {
			t.Errorf("valid Android /proc label refused: %q, %v", s, err)
		}
	}
	bad := []string{"", "u:r:", "untrusted_app:s0", base + "\x00\x00", base + "\n\n", base + "\r\n", base + "\x00x", "u:r:evil\x00_app:s0", base + " ", strings.Repeat("x", 195)}
	for _, s := range bad {
		if _, err := procSELinuxLabel([]byte(s)); err == nil {
			t.Errorf("unsafe /proc label accepted %q", s)
		}
	}
}

func TestPMBridgeAcceptsAndroidNULTerminatedProcContextButNotChangedLabel(t *testing.T) {
	pinned := "u:r:untrusted_app:s0:c79,c257,c512,c768"
	proc := &pmFakeProc{ticks: 42, uid: 10335, label: pinned + "\x00"}
	bridge := &PMBridge{Pin: AuthorityPeerPin{UID: 10335, SELinuxContext: pinned}, Proc: proc}
	if got, err := bridge.verifyPeer(901, 10335); err != nil || got != 42 {
		t.Fatalf("NUL-terminated real Android PM peer denied: %d %v", got, err)
	}
	proc.label = "u:r:other:s0\x00"
	if _, err := bridge.verifyPeer(901, 10335); err == nil {
		t.Fatal("changed Android authority context was accepted")
	}
	proc.label = pinned + "\x00forged"
	if _, err := bridge.verifyPeer(901, 10335); err == nil {
		t.Fatal("embedded null context was accepted")
	}
}

func TestAppAndRootVerifiersAcceptNULProcContextAndRejectUnsafeLabels(t *testing.T) {
	cert := strings.Repeat("a", 64)
	approved := "u:r:untrusted_app:s0:c79,c257,c512,c768"
	p := &fakeProc{uid: 10327, tick: 400, label: approved + "\x00"}
	v := &AndroidVerifier{Pins: map[uint32]PackagePin{10327: {Name: "com.mikeyphw.bkx.android", CertSHA256: cert, SELinuxContext: approved}}, Proc: p, Packages: &attestor{}}
	peer := brokeripc.KernelPeer{UID: 10327, GID: 10327, PID: 333}
	if _, err := v.VerifyPeer(peer); err != nil {
		t.Fatal("Android app NUL label:", err)
	}
	p.label = approved + "\x00hidden"
	if _, err := v.VerifyPeer(peer); err == nil {
		t.Fatal("Android app embedded NUL accepted")
	}
	r := &rootProc{ticks: 700, uid: 0, label: "u:r:su:s0\x00"}
	root := &RootVerifier{Pin: ModulePin{Name: "chrootctl", ModuleSealSHA256: cert, SELinuxContext: "u:r:su:s0"}, Proc: r, Modules: &rootModuleAttestor{}}
	if _, err := root.VerifyPeer(brokeripc.KernelPeer{PID: 501, UID: 0, GID: 0}); err != nil {
		t.Fatal("root module NUL label:", err)
	}
	r.label = "u:r:su:s0\x00forged"
	if _, err := root.VerifyPeer(brokeripc.KernelPeer{PID: 501, UID: 0, GID: 0}); err == nil {
		t.Fatal("root embedded NUL accepted")
	}
}
