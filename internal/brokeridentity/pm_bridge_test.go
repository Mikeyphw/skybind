package brokeridentity

import (
	"bufio"
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net"
	"os"
	"strings"
	"testing"
	"time"
)

type pmFakeProc struct {
	ticks uint64
	uid   uint32
	label string
}

func (p *pmFakeProc) Read(pid int32, field string) ([]byte, error) {
	switch field {
	case "stat":
		return []byte(fmt.Sprintf("%d (skybind main) S %s%d 0 0", pid, strings.Repeat("0 ", 18), p.ticks)), nil
	case "status":
		return []byte(fmt.Sprintf("Uid: %d %d %d %d\n", p.uid, p.uid, p.uid, p.uid)), nil
	case "attr/current":
		return []byte(p.label + "\n"), nil
	}
	return nil, ErrUnverified
}
func TestPMBridgeRejectsUnsafeAuthorityPin(t *testing.T) {
	p := &pmFakeProc{uid: 10327, ticks: 123, label: "u:r:untrusted_app:s0"}
	for _, pin := range []AuthorityPeerPin{{}, {UID: 0, SELinuxContext: p.label}, {UID: 10327, SELinuxContext: ""}, {UID: 10327, SELinuxContext: "u:r:wrong\n"}} {
		b := &PMBridge{Pin: pin, Proc: p}
		if b.validConfig() {
			t.Errorf("accepted unsafe pin: %#v", pin)
		}
	}
	good := &PMBridge{Pin: AuthorityPeerPin{UID: 10327, SELinuxContext: p.label}, Proc: p}
	if !good.validConfig() {
		t.Fatal("rejected good pin")
	}
	if _, e := good.verifyPeer(300, 10328); e == nil {
		t.Fatal("wrong peer uid accepted")
	}
	if _, e := good.verifyPeer(300, 10327); e != nil {
		t.Fatal(e)
	}
	p.label = "u:r:attacker:s0"
	if _, e := good.verifyPeer(300, 10327); e == nil {
		t.Fatal("mismatched SELinux accepted")
	}
	p.label = "u:r:untrusted_app:s0"
	p.uid = 10328
	if _, e := good.verifyPeer(300, 10327); e == nil {
		t.Fatal("mismatched /proc UID accepted")
	}
}
func TestPMMessageSchemaNegatives(t *testing.T) {
	base := `{"version":1,"nonce":"` + strings.Repeat("a", 64) + `","uid":10327,"package":"com.mikeyphw.bkx.android","record":{"uid":10327,"packages_for_uid":["com.mikeyphw.bkx.android"],"installed_package":"com.mikeyphw.bkx.android","signers_der_base64":["AA=="],"installed_for_user":true}}`
	if _, e := readPMMessage([]byte(base)); e != nil {
		t.Fatal(e)
	}
	samples := []string{
		strings.Replace(base, `"uid":10327`, `"uid":10327,"uid":10327`, 1),
		strings.Replace(base, `"installed_for_user":true`, `"installed_for_user":true,"uid":10327`, 1),
		strings.Replace(base, `"version":1`, `"version":2`, 1),
		strings.Replace(base, `"nonce":"`+strings.Repeat("a", 64)+`"`, `"nonce":"forged"`, 1),
		strings.Replace(base, `"package":"com.mikeyphw.bkx.android"`, `"package":"evil","surprise":true`, 1),
		base + ` {}`,
		strings.Repeat("A", pmMaxLine+1),
		"",
	}
	for i, s := range samples {
		if _, e := readPMMessage([]byte(s)); e == nil {
			t.Errorf("unsafe response %d accepted", i)
		}
	}
}
func TestPMRoundTripChallengeRejectsSpoofAndReplay(t *testing.T) {
	cases := []struct {
		name, mode string
		ok         bool
	}{
		{"valid", "ok", true}, {"replayed-nonce", "nonce", false}, {"uid-switch", "uid", false},
		{"package-switch", "package", false}, {"agent-denial", "error", false},
		{"missing-record", "nil-record", false}, {"oversized", "large", false},
		{"duplicate-json", "duplicate", false}, {"unknown-json", "unknown", false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			a, b := net.Pipe()
			defer a.Close()
			defer b.Close()
			go func() {
				reader := bufio.NewReader(b)
				line, e := reader.ReadBytes('\n')
				if e != nil {
					return
				}
				var m pmMessage
				_ = json.Unmarshal(line, &m)
				m.Record = &pmRecord{UID: m.UID, PackagesForUID: []string{m.Package}, InstalledPackage: m.Package, Signers: []string{base64.StdEncoding.EncodeToString([]byte(strings.Repeat("Z", 300)))}, IsInstalledForUser: true}
				switch tc.mode {
				case "nonce":
					m.Nonce = strings.Repeat("b", 64)
				case "uid":
					m.UID++
				case "package":
					m.Package = "com.forged.client"
				case "error":
					m.Error = "not_authorized"
				case "nil-record":
					m.Record = nil
				case "large":
					_, _ = b.Write([]byte(strings.Repeat("z", pmMaxLine+1)))
					return
				case "duplicate":
					raw, _ := json.Marshal(m)
					raw = append([]byte(`{"version":1,`), raw[1:]...)
					_, _ = b.Write(append(raw, '\n'))
					return
				case "unknown":
					raw, _ := json.Marshal(m)
					raw = append(raw[:len(raw)-1], []byte(`,"unknown":true}`)...)
					_, _ = b.Write(append(raw, '\n'))
					return
				}
				raw, _ := json.Marshal(m)
				_, _ = b.Write(append(raw, '\n'))
			}()
			req := pmMessage{Version: 1, Nonce: strings.Repeat("a", 64), UID: 10327, Package: "com.mikeyphw.bkx.android"}
			ctx, cancel := context.WithTimeout(context.Background(), time.Second)
			defer cancel()
			_, e := pmRoundTrip(ctx, a, req)
			if (e == nil) != tc.ok {
				t.Fatalf("expected ok=%v got %v", tc.ok, e)
			}
		})
	}
}
func TestPMBridgeRealUnixRoundtripToPlatformSigner(t *testing.T) {
	// Host fixture exercises same request/response serialization as Android.
	// Peer snapshots are injected only here; production Accept reads SO_PEERCRED.
	// Linux sockaddr_un.sun_path is limited to 108 bytes including the NUL.
	// Termux's TMPDIR is already long, and testing.T.TempDir extends it; using
	// that full filesystem path fails bind(2) with EINVAL on real Android.
	// Use a short, unique abstract address, just like the production PM bridge.
	// Hashing the test's unique temporary directory retains isolation without
	// making the socket path length depend on the host temporary-directory path.
	nameSeed := sha256.Sum256([]byte(t.TempDir()))
	addr := &net.UnixAddr{Name: "\x00skybind-r1-pm-test-" + hex.EncodeToString(nameSeed[:]), Net: "unix"}
	if len(addr.Name) > 107 {
		t.Fatalf("abstract test socket exceeds Linux sun_path limit: %d", len(addr.Name))
	}
	listener, e := net.ListenUnix("unix", addr)
	if e != nil {
		t.Fatal(e)
	}
	defer listener.Close()
	client, e := net.DialUnix("unix", nil, addr)
	if e != nil {
		t.Fatal(e)
	}
	defer client.Close()
	server, e := listener.AcceptUnix()
	if e != nil {
		t.Fatal(e)
	}
	proc := &pmFakeProc{uid: 10327, ticks: 568, label: "u:r:untrusted_app:s0"}
	bridge := &PMBridge{Pin: AuthorityPeerPin{UID: 10327, SELinuxContext: proc.label}, Proc: proc, conn: server, peerPID: 332, peerTicks: 568}
	defer bridge.Close()
	cert := []byte(strings.Repeat("Z", 300))
	sha := sha256.Sum256(cert)
	go func() {
		reader := bufio.NewReader(client)
		for {
			raw, e := reader.ReadBytes('\n')
			if e != nil {
				return
			}
			var request pmMessage
			if json.Unmarshal(raw, &request) != nil {
				return
			}
			request.Record = &pmRecord{UID: request.UID, PackagesForUID: []string{request.Package}, InstalledPackage: request.Package, Signers: []string{base64.StdEncoding.EncodeToString(cert)}, IsInstalledForUser: true}
			out, _ := json.Marshal(request)
			_, _ = client.Write(append(out, '\n'))
		}
	}()
	pin := PackagePin{Name: "com.mikeyphw.bkx.android", CertSHA256: hex.EncodeToString(sha[:]), SELinuxContext: proc.label}
	auth := PlatformPackageAttestor{Authority: bridge}
	if e := auth.Verify(context.Background(), 10327, pin); e != nil {
		t.Fatal("valid PM response denied:", e)
	}
	if e := auth.Verify(context.Background(), 10327, PackagePin{Name: pin.Name, CertSHA256: strings.Repeat("0", 64), SELinuxContext: pin.SELinuxContext}); e == nil {
		t.Fatal("wrong signer accepted")
	}
	proc.ticks++
	if e := auth.Verify(context.Background(), 10327, pin); e == nil {
		t.Fatal("PID reuse accepted")
	}
	if bridge.State() != "DISABLED" {
		t.Fatal("invalidated authority connection retained")
	}
}
func TestPMUnavailableNeverIssuesImplicitTrust(t *testing.T) {
	b := &PMBridge{Pin: AuthorityPeerPin{UID: 10327, SELinuxContext: "u:r:untrusted_app:s0"}, Proc: &pmFakeProc{uid: 10327, ticks: 200, label: "u:r:untrusted_app:s0"}}
	if _, e := b.LookupInstalled(context.Background(), 10327, "com.mikeyphw.bkx.android"); e == nil {
		t.Fatal("accepted offline authority")
	}
	if b.State() != "DISABLED" {
		t.Fatal("authority activated without operator")
	}
	if os.Geteuid() != 0 {
		if e := b.Listen(); e == nil {
			t.Fatal("unprivileged listener")
		}
	}
}
