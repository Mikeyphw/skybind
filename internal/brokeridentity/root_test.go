package brokeridentity

import (
	"context"
	"errors"
	"fmt"
	"skybind/internal/brokeripc"
	"strings"
	"testing"
)

type rootProc struct {
	ticks  int
	uid    uint32
	label  string
	change bool
	reads  int
}

func (p *rootProc) Read(pid int32, file string) ([]byte, error) {
	p.reads++
	switch file {
	case "stat":
		if p.change && p.reads > 3 {
			p.ticks++
		}
		return []byte(fmt.Sprintf("%d (chrootctl agent) S %s %d 0 0", pid, strings.TrimSpace(strings.Repeat("0 ", 18)), p.ticks)), nil
	case "status":
		return []byte(fmt.Sprintf("Name:\tchrootctl\nUid:\t%d\t%d\t%d\t%d\n", p.uid, p.uid, p.uid, p.uid)), nil
	case "attr/current":
		return []byte(p.label + "\n"), nil
	default:
		return nil, errors.New("untrusted_proc_path")
	}
}

type rootModuleAttestor struct {
	reject bool
	calls  int
}

func (a *rootModuleAttestor) VerifyModuleProcess(_ context.Context, _ int32, pin ModulePin) error {
	a.calls++
	if a.reject {
		return errors.New("module_seal_not_authenticated")
	}
	if pin.Name != "chrootctl" {
		return errors.New("wrong_module")
	}
	return nil
}
func TestRootWorkloadIdentityBoundToModuleSealAndSELinux(t *testing.T) {
	proc := &rootProc{ticks: 54321, label: "u:r:su:s0"}
	seal := strings.Repeat("a", 64)
	a := &rootModuleAttestor{}
	v := &RootVerifier{Pin: ModulePin{Name: "chrootctl", ModuleSealSHA256: seal, SELinuxContext: "u:r:su:s0"}, Proc: proc, Modules: a}
	peer := brokeripc.KernelPeer{UID: 0, GID: 0, PID: 321}
	id, err := v.VerifyPeer(peer)
	if err != nil || id.UID != 0 || len(id.ProcessKey) != 64 || a.calls != 1 {
		t.Fatalf("verified root workload failed %+v %v", id, err)
	}
	proc.ticks++
	updated, err := v.VerifyPeer(peer)
	if err != nil || updated.ProcessKey == id.ProcessKey {
		t.Fatal("PID reuse not isolated", err)
	}
	proc.label = "u:r:untrusted_app:s0"
	if _, err = v.VerifyPeer(peer); err == nil {
		t.Fatal("wrong SELinux context accepted")
	}
	proc.label = "u:r:su:s0"
	a.reject = true
	if _, err = v.VerifyPeer(peer); err == nil {
		t.Fatal("module attestation bypass")
	}
	a.reject = false
	proc.change = true
	if _, err = v.VerifyPeer(peer); err == nil {
		t.Fatal("PID start-time race accepted")
	}
}
func TestRootVerifierFailClosed(t *testing.T) {
	a := &rootModuleAttestor{}
	p := &rootProc{ticks: 55, label: "u:r:su:s0"}
	mk := func() *RootVerifier {
		return &RootVerifier{Proc: p, Modules: a, Pin: ModulePin{Name: "chrootctl", ModuleSealSHA256: strings.Repeat("a", 64), SELinuxContext: "u:r:su:s0"}}
	}
	good := brokeripc.KernelPeer{UID: 0, GID: 0, PID: 43}
	cases := []struct {
		name   string
		change func(*RootVerifier, *brokeripc.KernelPeer)
	}{
		{"wrong module", func(v *RootVerifier, _ *brokeripc.KernelPeer) { v.Pin.Name = "other" }},
		{"missing seal", func(v *RootVerifier, _ *brokeripc.KernelPeer) { v.Pin.ModuleSealSHA256 = "" }},
		{"wrong root uid", func(_ *RootVerifier, p *brokeripc.KernelPeer) { p.UID = 10000 }},
		{"wrong root gid", func(_ *RootVerifier, p *brokeripc.KernelPeer) { p.GID = 10000 }},
		{"missing module attestor", func(v *RootVerifier, _ *brokeripc.KernelPeer) { v.Modules = nil }},
		{"missing proc", func(v *RootVerifier, _ *brokeripc.KernelPeer) { v.Proc = nil }},
		{"invalid pid", func(_ *RootVerifier, p *brokeripc.KernelPeer) { p.PID = 0 }},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			v := mk()
			peer := good
			tc.change(v, &peer)
			if _, err := v.VerifyPeer(peer); err == nil {
				t.Fatal("untrusted root accepted")
			}
		})
	}
}
func TestAndroidProcReaderAllowsOnlyExactRootLabelPath(t *testing.T) {
	pr := LinuxProc{}
	for _, p := range []string{"../attr/current", "attr/../../etc/passwd", "attr/other", "cmdline"} {
		if _, err := pr.Read(12345, p); err == nil {
			t.Fatal("unsafe proc path allowed", p)
		}
	}
}
