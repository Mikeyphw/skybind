package brokeripc

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"net"
	"os"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"skybind/internal/brokergrant"
)

func testAbstractName(t *testing.T) string {
	t.Helper()
	seed := sha256.Sum256([]byte(t.TempDir()))
	return "\x00skybind-r1-broker-test-" + hex.EncodeToString(seed[:16])
}

func TestAbstractConsumerDefaultDeny(t *testing.T) {
	g := &AbstractConsumerSocket{}
	if e := g.Start(); e == nil {
		t.Fatal("default activated")
	}
	g.ExplicitlyEnabled = true
	g.BKXUID = 10327
	g.Grants = brokergrant.New()
	if e := g.Start(); e == nil {
		t.Fatal("started without verifier/backend")
	}
	g.Verifier = localVerifier{identity: brokergrant.Identity{UID: uint32(os.Getuid()), ProcessKey: "only-test"}}
	if e := g.Start(); e == nil {
		t.Fatal("started without backend")
	}
	g.Backend = func(Request) (json.RawMessage, error) { return json.RawMessage(`{}`), nil }
	if os.Geteuid() != 0 {
		if e := g.Start(); e == nil {
			t.Fatal("nonroot activated abstract socket")
		}
	}
}

func TestAbstractConsumerRealKernelPeerGrantAndRevocation(t *testing.T) {
	if os.Geteuid() != 0 {
		t.Skip("root-only listener; hosted CI must run sudo Go tests")
	}
	identity := brokergrant.Identity{UID: uint32(os.Getuid()), ProcessKey: "root-fixture-authority-bound"}
	grants := brokergrant.New()
	var calls atomic.Int32
	endpoint := testAbstractName(t)
	g := &AbstractConsumerSocket{BKXUID: 10327, ExplicitlyEnabled: true, Grants: grants,
		Verifier: localVerifier{identity: identity}, Backend: func(r Request) (json.RawMessage, error) {
			calls.Add(1)
			return json.RawMessage(`{"fixture":"safe"}`), nil
		}}
	if e := g.startAt(endpoint); e != nil {
		t.Fatal(e)
	}
	defer g.Close()
	if e := g.startAt(endpoint); e == nil {
		t.Fatal("duplicate listener accepted")
	}
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() { done <- g.Serve(ctx) }()
	send := func(token, remote, path, op string) Response {
		t.Helper()
		res, e := requestAt(context.Background(), endpoint, Request{Version: 1, Token: token, Operation: op, Remote: remote, Path: path})
		if e != nil {
			t.Fatal(e)
		}
		return res
	}
	denied := strings.Repeat("0", 64)
	if res := send(denied, "drive", "safe", "rclone.version"); res.OK || calls.Load() != 0 {
		t.Fatal("no-grant request reached backend", res)
	}
	token, receipt, e := grants.Issue(brokergrant.GrantSpec{Caller: identity, Remote: "drive", Prefix: "safe", Operations: []string{"rclone.version"}, TTL: time.Minute})
	if e != nil {
		t.Fatal(e)
	}
	if res := send(token, "drive", "safe/folder", "rclone.version"); !res.OK || calls.Load() != 1 {
		t.Fatal("approved read failed", res)
	}
	for _, tc := range []struct{ remote, path, op string }{
		{"other", "safe", "rclone.version"},
		{"drive", "safeevil", "rclone.version"},
		{"drive", "safe", "rclone.rcat"},
		{"drive", "../safe", "rclone.version"},
	} {
		res := send(token, tc.remote, tc.path, tc.op)
		if res.OK || calls.Load() != 1 {
			t.Fatal("scope escaped", tc, res)
		}
	}
	if !grants.Revoke(receipt.ID) {
		t.Fatal("grant not revoked")
	}
	if res := send(token, "drive", "safe", "rclone.version"); res.OK || calls.Load() != 1 {
		t.Fatal("revoked token reached backend", res)
	}
	cancel()
	select {
	case e := <-done:
		if e != nil {
			t.Fatal(e)
		}
	case <-time.After(8 * time.Second):
		t.Fatal("server did not close")
	}
	if e := g.Close(); e != nil && !errors.Is(e, net.ErrClosed) {
		t.Fatal(e)
	}
	if c, e := net.DialTimeout("unix", endpoint, 100*time.Millisecond); e == nil {
		c.Close()
		t.Fatal("listener remained open")
	}
}

func TestAbstractConsumerRejectsWrongKernelPeer(t *testing.T) {
	if os.Geteuid() != 0 {
		t.Skip("root-owned socket fixture")
	}
	endpoint := testAbstractName(t)
	g := &AbstractConsumerSocket{BKXUID: 10327, ExplicitlyEnabled: true, Grants: brokergrant.New(),
		Verifier: localVerifier{identity: brokergrant.Identity{UID: 10327, ProcessKey: "pinned-bkx"}},
		Backend:  func(Request) (json.RawMessage, error) { t.Fatal("wrong UID accessed backend"); return nil, nil }}
	if e := g.startAt(endpoint); e != nil {
		t.Fatal(e)
	}
	defer g.Close()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	done := make(chan error, 1)
	go func() { done <- g.Serve(ctx) }()
	res, e := requestAt(context.Background(), endpoint, Request{Version: 1, Token: strings.Repeat("0", 64), Operation: "rclone.version", Remote: "drive"})
	if res.OK {
		t.Fatal("bad kernel peer accepted", res, e)
	}
	// An unauthenticated peer may receive a denial or a connection reset.
	// Neither can expose backend data or a successful broker result.
	cancel()
	select {
	case <-done:
	case <-time.After(8 * time.Second):
		t.Fatal("server shutdown stuck")
	}
}
