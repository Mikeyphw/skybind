package brokerruntime

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net"
	"os"
	"skybind/internal/brokeripc"
	"strings"
	"testing"
	"time"
)

func rootHandoffFixture(t *testing.T) (*GrantHandoff, *fakeProc, brokeripc.KernelPeer) {
	t.Helper()
	p := policyFixture()
	cert := []byte(strings.Repeat("S", 300))
	sum := sha256.Sum256(cert)
	p.BKX.CertSHA256 = hex.EncodeToString(sum[:])
	proc := &fakeProc{uid: 0, label: p.Chrootctl.SELinuxContext, tick: 234}
	g, e := Assemble(p, Dependencies{PlatformAuthority: &fakePM{signer: cert}, Proc: proc, ModuleAuthority: &fakeModule{}, Backend: func(r brokeripc.Request) (json.RawMessage, error) { return json.RawMessage(`{"safe":true}`), nil }})
	if e != nil {
		t.Fatal(e)
	}
	h := &GrantHandoff{Gateway: g}
	if e = h.Start(); e != nil {
		t.Fatal(e)
	}
	return h, proc, brokeripc.KernelPeer{UID: 0, GID: 0, PID: int32(os.Getpid())}
}
func TestHandoffOneShotExactKernelPIDAndRevocation(t *testing.T) {
	if os.Geteuid() != 0 {
		t.Skip("root-only kernel peer test")
	}
	h, proc, peer := rootHandoffFixture(t)
	defer h.Close()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	done := make(chan error, 1)
	go func() { done <- h.Serve(ctx) }()
	offer := HandoffRequest{Consumer: "chrootctl", Remote: "test", Prefix: "safe", Operations: []string{"rclone.version"}, TTL: time.Minute}
	if e := h.Approve(peer, offer); e != nil {
		t.Fatal(e)
	}
	c, e := net.DialTimeout("unix", GrantHandoffEndpoint, 2*time.Second)
	if e != nil {
		t.Fatal(e)
	}
	var delivered struct {
		Version   int       `json:"version"`
		Token     string    `json:"token"`
		ExpiresAt time.Time `json:"expires_at"`
	}
	if e = json.NewDecoder(c).Decode(&delivered); e != nil {
		t.Fatal(e)
	}
	_ = c.Close()
	if delivered.Version != 1 || len(delivered.Token) != 64 {
		t.Fatal("handoff did not deliver approved grant")
	}
	identity, e := h.Gateway.Verifier.VerifyPeer(peer)
	if e != nil {
		t.Fatal(e)
	}
	if e = h.Gateway.Grants.Authorize(delivered.Token, identity, "rclone.version", "test", "safe/child"); e != nil {
		t.Fatal(e)
	}
	if e = h.Gateway.Grants.Authorize(delivered.Token, identity, "rclone.version", "test", "safeevil"); e == nil {
		t.Fatal("path escape authorized")
	}
	if e = h.Gateway.Grants.Authorize(delivered.Token, identity, "rclone.rcat", "test", "safe"); e == nil {
		t.Fatal("write authorized")
	}
	if e = h.Gateway.Grants.Authorize(delivered.Token, identity, "rclone.version", "else", "safe"); e == nil {
		t.Fatal("wrong remote authorized")
	}
	if len(h.IssuedReceiptIDs()) != 1 {
		t.Fatal("receipt missing")
	}
	if !h.RevokeIssued(h.IssuedReceiptIDs()[0]) {
		t.Fatal("revocation failed")
	}
	if e = h.Gateway.Grants.Authorize(delivered.Token, identity, "rclone.version", "test", "safe"); e == nil {
		t.Fatal("revoked token accepted")
	}
	if c, e = net.DialTimeout("unix", GrantHandoffEndpoint, 2*time.Second); e == nil {
		_ = c.SetReadDeadline(time.Now().Add(200 * time.Millisecond))
		var v any
		err := json.NewDecoder(c).Decode(&v)
		_ = c.Close()
		if err == nil {
			t.Fatal("grant replay accepted")
		}
	}
	proc.tick++
	if e = h.Approve(peer, offer); e != nil {
		t.Fatalf("fresh process incarnation should be independently approved: %v", e)
	}
	cancel()
	select {
	case <-done:
	case <-time.After(time.Second * 3):
		t.Fatal("handoff listener did not shut down")
	}
}
func TestHandoffPolicyAndPeerDenials(t *testing.T) {
	if os.Geteuid() != 0 {
		t.Skip("root-only handoff")
	}
	h, _, peer := rootHandoffFixture(t)
	defer h.Close()
	for _, req := range []HandoffRequest{
		{Consumer: "chrootctl", Remote: "other", Prefix: "safe", Operations: []string{"rclone.version"}, TTL: time.Minute},
		{Consumer: "chrootctl", Remote: "test", Prefix: "safe", Operations: []string{"rclone.rcat"}, TTL: time.Minute},
		{Consumer: "chrootctl", Remote: "test", Prefix: "safe", Operations: []string{"rclone.version"}, TTL: 0},
		{Consumer: "chrootctl", Remote: "test", Prefix: "safe", Operations: []string{"rclone.version"}, TTL: 6 * time.Minute},
		{Consumer: "bkx", Remote: "test", Prefix: "safe", Operations: []string{"rclone.version"}, TTL: time.Minute},
	} {
		if e := h.Approve(peer, req); e == nil {
			t.Fatalf("accepted unapproved request: %v", req)
		}
	}
	if e := h.Approve(brokeripc.KernelPeer{UID: 1234, GID: 1234, PID: peer.PID}, HandoffRequest{Consumer: "chrootctl", Remote: "test", Prefix: "safe", Operations: []string{"rclone.version"}, TTL: time.Minute}); e == nil {
		t.Fatal("wrong identity approved")
	}
	if ids := h.IssuedReceiptIDs(); len(ids) != 0 {
		t.Fatal(fmt.Sprintf("denied request created grants: %v", ids))
	}
}
