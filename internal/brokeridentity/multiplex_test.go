package brokeridentity

import (
	"skybind/internal/brokeripc"
	"strings"
	"testing"
)

func TestDistinctBKXAndChrootctlPrincipals(t *testing.T) {
	app := &fakeProc{uid: 10327, tick: 999, label: "u:r:untrusted_app:s0:c123,c456"}
	trustedAndroid := &AndroidVerifier{Pins: map[uint32]PackagePin{10327: {Name: "com.mikeyphw.bkx.android", CertSHA256: strings.Repeat("a", 64), SELinuxContext: app.label}}, Packages: &attestor{}, Proc: app}
	root := &rootProc{ticks: 1001, label: "u:r:su:s0"}
	trustedRoot := &RootVerifier{Pin: ModulePin{Name: "chrootctl", ModuleSealSHA256: strings.Repeat("b", 64), SELinuxContext: root.label}, Modules: &rootModuleAttestor{}, Proc: root}
	mux := ConsumerVerifier{BKXUID: 10327, BKX: trustedAndroid, Chrootctl: trustedRoot}
	pBKX := brokeripc.KernelPeer{UID: 10327, GID: 10327, PID: 100}
	pRoot := brokeripc.KernelPeer{UID: 0, GID: 0, PID: 101}
	bkxID, e := mux.VerifyPeer(pBKX)
	if e != nil {
		t.Fatal(e)
	}
	rootID, e := mux.VerifyPeer(pRoot)
	if e != nil {
		t.Fatal(e)
	}
	if bkxID.ProcessKey == rootID.ProcessKey || bkxID.UID == rootID.UID {
		t.Fatal("identities merged")
	}
	for _, p := range []brokeripc.KernelPeer{{UID: 10328, GID: 10328, PID: 100}, {UID: 10327, GID: 0, PID: 100}, {UID: 0, GID: 1025, PID: 101}, {UID: 65534, GID: 65534, PID: 101}} {
		if _, e := mux.VerifyPeer(p); e == nil {
			t.Fatal("unauthorized peer accepted", p)
		}
	}
	mux.BKX = nil
	if _, e = mux.VerifyPeer(pBKX); e == nil {
		t.Fatal("nil app verifier accepted")
	}
	mux.Chrootctl = nil
	if _, e = mux.VerifyPeer(pRoot); e == nil {
		t.Fatal("nil root verifier accepted")
	}
}
