package brokerruntime

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"skybind/internal/brokeridentity"
	"skybind/internal/brokeripc"
)

func policyFixture() Policy {
	return Policy{
		Schema: Schema, ABI: 1, ExplicitlyEnabled: true,
		BKX:       BKXPin{Package: "com.mikeyphw.bkx.android", UID: 10327, CertSHA256: strings.Repeat("a", 64), SELinuxContext: "u:r:untrusted_app:s0:c123,c456"},
		Chrootctl: ChrootPin{ManifestSHA256: strings.Repeat("b", 64), SELinuxContext: "u:r:su:s0"},
		Rules:     []Rule{{Consumer: "bkx", Remote: "test", Prefix: "safe", Operations: []string{"rclone.version"}}, {Consumer: "chrootctl", Remote: "test", Prefix: "safe", Operations: []string{"rclone.version"}}},
	}
}
func TestOperatorPolicyFailClosed(t *testing.T) {
	good := policyFixture()
	if err := good.Validate(); err != nil {
		t.Fatal(err)
	}
	bad := []struct {
		name   string
		mutate func(*Policy)
	}{
		{"default-disabled", func(p *Policy) { p.ExplicitlyEnabled = false }},
		{"wrong-abi", func(p *Policy) { p.ABI = 2 }},
		{"invalid-package", func(p *Policy) { p.BKX.Package = ".." }},
		{"missing-signer", func(p *Policy) { p.BKX.CertSHA256 = "" }},
		{"missing-selinux", func(p *Policy) { p.Chrootctl.SELinuxContext = "" }},
		{"unknown-client", func(p *Policy) { p.Rules[0].Consumer = "other" }},
		{"write", func(p *Policy) { p.Rules[0].Operations = []string{"rclone.rcat"} }},
		{"duplicate-ops", func(p *Policy) { p.Rules[0].Operations = []string{"rclone.version", "rclone.version"} }},
		{"path-traversal", func(p *Policy) { p.Rules[0].Prefix = "safe/../private" }},
		{"path-root", func(p *Policy) { p.Rules[0].Prefix = "/data/adb" }},
		{"different-user", func(p *Policy) { p.BKX.UID = 0 }},
		{"empty-rules", func(p *Policy) { p.Rules = nil }},
		{"duplicate-grants", func(p *Policy) { p.Rules = append(p.Rules, p.Rules[0]) }},
	}
	for _, tc := range bad {
		t.Run(tc.name, func(t *testing.T) {
			p := policyFixture()
			tc.mutate(&p)
			if p.Validate() == nil {
				t.Fatal("approved unsafe policy")
			}
		})
	}
}
func TestLoadRootOwnedOperatorPolicyAndRejectSymlinks(t *testing.T) {
	if os.Geteuid() != 0 {
		t.Skip("requires root-owned files")
	}
	dir := filepath.Join(t.TempDir(), "protected")
	if e := os.Mkdir(dir, 0700); e != nil {
		t.Fatal(e)
	}
	path := filepath.Join(dir, "policy.json")
	p := policyFixture()
	b, _ := json.Marshal(p)
	if e := os.WriteFile(path, b, 0600); e != nil {
		t.Fatal(e)
	}
	if got, e := LoadAt(path); e != nil || got.BKX.UID != p.BKX.UID {
		t.Fatal(e)
	}
	for _, tc := range []struct {
		name    string
		prepare func() error
		restore func() error
	}{
		{"public-policy", func() error { return os.Chmod(path, 0644) }, func() error { return os.Chmod(path, 0600) }},
		{"public-parent", func() error { return os.Chmod(dir, 0755) }, func() error { return os.Chmod(dir, 0700) }},
		{"invalid-json", func() error { return os.WriteFile(path, []byte(`{"schema":"forged"}`), 0600) }, func() error { return os.WriteFile(path, b, 0600) }},
		{"trailing-json", func() error { return os.WriteFile(path, append(append([]byte{}, b...), []byte(` {}`)...), 0600) }, func() error { return os.WriteFile(path, b, 0600) }},
	} {
		t.Run(tc.name, func(t *testing.T) {
			if e := tc.prepare(); e != nil {
				t.Fatal(e)
			}
			if _, e := LoadAt(path); e == nil {
				t.Fatal("unsafe policy accepted")
			}
			if e := tc.restore(); e != nil {
				t.Fatal(e)
			}
		})
	}
	if e := os.Remove(path); e != nil {
		t.Fatal(e)
	}
	target := filepath.Join(dir, "target")
	if e := os.WriteFile(target, b, 0600); e != nil {
		t.Fatal(e)
	}
	if e := os.Symlink(target, path); e != nil {
		t.Fatal(e)
	}
	if _, e := LoadAt(path); e == nil {
		t.Fatal("symlink accepted")
	}
}

type fakeProc struct {
	uid    uint32
	label  string
	tick   int
	change bool
}

func (p *fakeProc) Read(pid int32, file string) ([]byte, error) {
	switch file {
	case "stat":
		return []byte(fmt.Sprintf("%d (client) S %s %d 0 0", pid, strings.TrimSpace(strings.Repeat("0 ", 18)), p.tick)), nil
	case "status":
		return []byte(fmt.Sprintf("Uid: %d %d %d %d\n", p.uid, p.uid, p.uid, p.uid)), nil
	case "attr/current":
		return []byte(p.label + "\n"), nil
	default:
		return nil, errors.New("unsafe")
	}
}

type fakePM struct {
	signer  []byte
	changed bool
}

func (p *fakePM) LookupInstalled(ctx context.Context, uid uint32, pkg string) (brokeridentity.PlatformPackageRecord, error) {
	if p.changed {
		return brokeridentity.PlatformPackageRecord{}, errors.New("revoked")
	}
	return brokeridentity.PlatformPackageRecord{UID: uid, PackagesForUID: []string{pkg}, InstalledPackage: pkg, APKContentsSigners: [][]byte{p.signer}, IsInstalledForUser: true}, nil
}

type fakeModule struct{ err error }

func (f *fakeModule) VerifyModuleProcess(ctx context.Context, pid int32, pin brokeridentity.ModulePin) error {
	return f.err
}
func TestVerifiedScopedGrantAndImmediateRevocation(t *testing.T) {
	p := policyFixture()
	cert := []byte(strings.Repeat("Z", 300))
	d := sha256.Sum256(cert)
	p.BKX.CertSHA256 = hex.EncodeToString(d[:])
	proc := &fakeProc{uid: p.BKX.UID, tick: 225, label: p.BKX.SELinuxContext}
	pm := &fakePM{signer: cert}
	auth := Dependencies{PlatformAuthority: pm, Proc: proc, ModuleAuthority: &fakeModule{}, Backend: func(r brokeripc.Request) (json.RawMessage, error) { return json.RawMessage(`{"ok":true}`), nil }}
	for _, tc := range []struct {
		name   string
		change func(*Dependencies)
	}{
		{"no-platform-authority", func(d *Dependencies) { d.PlatformAuthority = nil }},
		{"no-proc", func(d *Dependencies) { d.Proc = nil }},
		{"no-module-attestor", func(d *Dependencies) { d.ModuleAuthority = nil }},
		{"no-backend", func(d *Dependencies) { d.Backend = nil }},
	} {
		t.Run(tc.name, func(t *testing.T) {
			missing := auth
			tc.change(&missing)
			if _, e := Assemble(p, missing); e == nil {
				t.Fatal("missing trusted authority accepted")
			}
		})
	}
	g, e := Assemble(p, auth)
	if e != nil {
		t.Fatal(e)
	}
	peer := brokeripc.KernelPeer{UID: p.BKX.UID, GID: p.BKX.UID, PID: 319}
	if _, _, e = g.IssueApproved(peer, "bkx", "test", "safe", []string{"rclone.version"}, time.Minute); e != nil {
		t.Fatal(e)
	}
	if _, _, e = g.IssueApproved(peer, "bkx", "test", "safe/sub", []string{"rclone.version"}, time.Minute); e == nil {
		t.Fatal("scope escalation accepted")
	}
	if _, _, e = g.IssueApproved(peer, "bkx", "other", "safe", []string{"rclone.version"}, time.Minute); e == nil {
		t.Fatal("cross remote accepted")
	}
	if _, _, e = g.IssueApproved(peer, "bkx", "test", "safe", []string{"rclone.copy"}, time.Minute); e == nil {
		t.Fatal("unapproved mutation accepted")
	}
	if _, _, e = g.IssueApproved(peer, "chrootctl", "test", "safe", []string{"rclone.version"}, time.Minute); e == nil {
		t.Fatal("app impersonated module")
	}
	if _, _, e = g.IssueApproved(peer, "bkx", "test", "safe", []string{"rclone.version"}, 10*time.Minute); e == nil {
		t.Fatal("excess TTL accepted")
	}
	token, rec, e := g.IssueApproved(peer, "bkx", "test", "safe", []string{"rclone.version"}, time.Minute)
	if e != nil {
		t.Fatal(e)
	}
	identity, e := g.Verifier.VerifyPeer(peer)
	if e != nil {
		t.Fatal(e)
	}
	if e = g.Grants.Authorize(token, identity, "rclone.version", "test", "safe/nested"); e != nil {
		t.Fatal(e)
	}
	if e = g.Grants.Authorize(token, identity, "rclone.version", "test", "safeevil"); e == nil {
		t.Fatal("prefix boundary escaped")
	}
	if !g.Revoke(rec.ID) {
		t.Fatal("revoke failed")
	}
	if e = g.Grants.Authorize(token, identity, "rclone.version", "test", "safe"); e == nil {
		t.Fatal("revoked token accepted")
	}
	pm.changed = true
	if _, _, e = g.IssueApproved(peer, "bkx", "test", "safe", []string{"rclone.version"}, time.Minute); e == nil {
		t.Fatal("package signer removed, grant still issued")
	}
	pm.changed = false
	proc.tick++
	newIdentity, e := g.Verifier.VerifyPeer(peer)
	if e != nil || newIdentity == identity {
		t.Fatal("pid reuse unbound", e)
	}
}
