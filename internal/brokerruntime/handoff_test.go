package brokerruntime

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
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

// The live operator needs causal diagnostics without leaking identities, raw
// errors, credentials, or tokens. This test runs without root or sockets.
func TestHandoffDiagnosticCodesAreBoundedAndResettable(t *testing.T) {
	h := &GrantHandoff{}
	h.mu.Lock()
	h.recordOutcomeLocked(errors.New("r1_handoff_no_approval"))
	h.recordOutcomeLocked(errors.New("r1_handoff_wrong_process"))
	h.recordOutcomeLocked(errors.New("secret-token=UNTRUSTED client/path"))
	h.recordOutcomeLocked(nil)
	h.mu.Unlock()

	d := h.Diagnostics()
	if d.Attempts != 4 || d.Delivered != 1 || d.Rejections != 3 || d.OfferPending ||
		d.LastRejection != "r1_handoff_issue_or_encoding_denied" ||
		d.RejectionCounts["r1_handoff_no_approval"] != 1 ||
		d.RejectionCounts["r1_handoff_wrong_process"] != 1 ||
		d.RejectionCounts["r1_handoff_issue_or_encoding_denied"] != 1 {
		t.Fatalf("wrong bounded summary: %+v", d)
	}
	data, e := json.Marshal(d)
	if e != nil || strings.Contains(string(data), "secret") || strings.Contains(string(data), "UNTRUSTED") ||
		strings.Contains(string(data), "token=") {
		t.Fatalf("operator diagnostic leaked unsanitized error: %q, %v", data, e)
	}
	d.RejectionCounts["r1_handoff_wrong_process"] = 99
	if h.Diagnostics().RejectionCounts["r1_handoff_wrong_process"] != 1 {
		t.Fatal("diagnostic snapshot mutates privileged state")
	}
	if v := (&GrantHandoff{}).Diagnostics(); v.Attempts != 0 || v.Rejections != 0 || v.OfferPending {
		t.Fatal("fresh gateway diagnostics are not fail-closed")
	}
}

// Reproduce the Android failure: the root policy authorizes five read-only
// operations but one exact-PID operator approval asks for only one. The
// resulting grant must never inherit the rest of the operator allowlist.
func TestGatewayNarrowOneOperationFromFiveOperationPolicy(t *testing.T) {
	if os.Geteuid() != 0 {
		t.Skip("root-only kernel peer test")
	}
	h, _, peer := rootHandoffFixture(t)
	defer h.Close()
	full := []string{"system.capabilities", "rclone.version", "rclone.listremotes", "rclone.lsjson", "rclone.size"}
	for i := range h.Gateway.policy.Rules {
		if h.Gateway.policy.Rules[i].Consumer == "chrootctl" {
			h.Gateway.policy.Rules[i].Operations = full
		}
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	finished := make(chan error, 1)
	go func() { finished <- h.Serve(ctx) }()
	op := "system.capabilities"
	if err := h.Approve(peer, HandoffRequest{Consumer: "chrootctl", Remote: "test", Prefix: "safe", Operations: []string{op}, TTL: time.Minute}); err != nil {
		t.Fatalf("one-op approval rejected: %v", err)
	}
	c, err := net.DialTimeout("unix", GrantHandoffEndpoint, time.Second*2)
	if err != nil {
		t.Fatal(err)
	}
	var delivered struct {
		Version   int       `json:"version"`
		Token     string    `json:"token"`
		ExpiresAt time.Time `json:"expires_at"`
	}
	err = json.NewDecoder(c).Decode(&delivered)
	_ = c.Close()
	if err != nil || delivered.Version != 1 || len(delivered.Token) != 64 {
		t.Fatalf("approved one-op grant was not delivered: %v", err)
	}
	identity, err := h.Gateway.Verifier.VerifyPeer(peer)
	if err != nil {
		t.Fatal(err)
	}
	if err := h.Gateway.Grants.Authorize(delivered.Token, identity, op, "test", "safe"); err != nil {
		t.Fatalf("issued one-op token denied its own scope: %v", err)
	}
	for _, other := range full[1:] {
		if err := h.Gateway.Grants.Authorize(delivered.Token, identity, other, "test", "safe"); err == nil {
			t.Fatalf("one-op token inherited unapproved operation %s", other)
		}
	}
	if d := h.Diagnostics(); d.Delivered != 1 || d.Rejections != 0 || d.OfferPending {
		t.Fatalf("grant handoff was not completed: %+v", d)
	}
	for _, id := range h.IssuedReceiptIDs() {
		if !h.RevokeIssued(id) {
			t.Fatal("failed to revoke narrowed grant")
		}
	}
	if err := h.Gateway.Grants.Authorize(delivered.Token, identity, op, "test", "safe"); err == nil {
		t.Fatal("revoked one-op token remained live")
	}
	cancel()
	select {
	case err := <-finished:
		if err != nil {
			t.Fatal(err)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("handoff socket did not shut down")
	}
}
