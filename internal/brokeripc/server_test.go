package brokeripc

import (
	"encoding/json"
	"errors"
	"net"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"skybind/internal/brokergrant"
)

type fakeVerifier struct {
	identity brokergrant.Identity
	err      error
}

func (v fakeVerifier) VerifyPeer(KernelPeer) (brokergrant.Identity, error) { return v.identity, v.err }

func roundTrip(t *testing.T, s *Server, body string) (Response, error) {
	t.Helper()
	dir, err := os.MkdirTemp("", "sbipc-")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(dir)
	sock := filepath.Join(dir, "s")
	a, err := net.ListenUnix("unix", &net.UnixAddr{Name: sock, Net: "unix"})
	if err != nil {
		t.Fatal(err)
	}
	defer a.Close()
	ch := make(chan error, 1)
	go func() {
		c, err := a.AcceptUnix()
		if err != nil {
			ch <- err
			return
		}
		ch <- s.ServeConn(c)
	}()
	c, err := net.DialUnix("unix", nil, &net.UnixAddr{Name: sock, Net: "unix"})
	if err != nil {
		t.Fatal(err)
	}
	_ = c.SetDeadline(time.Now().Add(6 * time.Second))
	if _, err := c.Write([]byte(body)); err != nil {
		t.Fatal(err)
	}
	if err := c.CloseWrite(); err != nil {
		t.Fatal(err)
	}
	var response Response
	err = json.NewDecoder(c).Decode(&response)
	c.Close()
	if err != nil {
		t.Fatal(err)
	}
	return response, <-ch
}

func TestKernelBoundAuthorizedRead(t *testing.T) {
	peer := brokergrant.Identity{UID: uint32(os.Getuid()), ProcessKey: "trusted-test-identity"}
	store := brokergrant.New()
	token, _, err := store.Issue(brokergrant.GrantSpec{Caller: peer, Remote: "drive", Prefix: "bkx/repo", Operations: []string{"rclone.lsjson"}, TTL: time.Minute})
	if err != nil {
		t.Fatal(err)
	}
	var count atomic.Int32
	s := &Server{Grants: store, Verifier: fakeVerifier{identity: peer}, Read: func(r Request) (json.RawMessage, error) {
		count.Add(1)
		return json.RawMessage(`{"entries":[]}`), nil
	}}
	request := `{"version":1,"token":"` + token + `","operation":"rclone.lsjson","remote":"drive","path":"bkx/repo/x"}`
	result, err := roundTrip(t, s, request)
	if err != nil || !result.OK || count.Load() != 1 {
		t.Fatalf("authorized read: %+v %v", result, err)
	}
	for _, forbidden := range []string{
		strings.Replace(request, "bkx/repo/x", "bkx/repoz/x", 1),
		strings.Replace(request, "rclone.lsjson", "rclone.deletefile", 1),
		strings.Replace(request, token, strings.Repeat("0", 64), 1),
		strings.TrimSuffix(request, "}") + `,"uid":0}`,
		request + request,
		strings.Repeat("x", MaxRequestBytes+1),
	} {
		r, e := roundTrip(t, s, forbidden)
		if e == nil || r.OK || count.Load() != 1 {
			t.Fatalf("accepted forbidden request: %+v %v", r, e)
		}
	}
}

func TestMissingAndSpoofedVerifierDenied(t *testing.T) {
	identity := brokergrant.Identity{UID: uint32(os.Getuid()), ProcessKey: "trusted"}
	store := brokergrant.New()
	token, _, err := store.Issue(brokergrant.GrantSpec{Caller: identity, Remote: "drive", Operations: []string{"rclone.version"}, TTL: time.Minute})
	if err != nil {
		t.Fatal(err)
	}
	var calls atomic.Int32
	s := &Server{Grants: store, Read: func(Request) (json.RawMessage, error) { calls.Add(1); return json.RawMessage(`{}`), nil }}
	req := `{"version":1,"token":"` + token + `","operation":"rclone.version","remote":"drive","path":""}`
	for _, verifier := range []Verifier{nil, fakeVerifier{identity: brokergrant.Identity{UID: identity.UID + 1, ProcessKey: "trusted"}}, fakeVerifier{err: errors.New("bad_sig")}, fakeVerifier{identity: brokergrant.Identity{UID: identity.UID}}} {
		s.Verifier = verifier
		res, err := roundTrip(t, s, req)
		if err == nil || res.OK || calls.Load() > 0 {
			t.Fatalf("unauthorized verifier accepted %+v %v", res, err)
		}
	}
	// Even the correct identity must not authorize a revoked token.
	s.Verifier = fakeVerifier{identity: identity}
	_, receipt, err := store.Issue(brokergrant.GrantSpec{Caller: identity, Remote: "drive", Operations: []string{"rclone.version"}, TTL: time.Minute})
	if err != nil || !store.Revoke(receipt.ID) {
		t.Fatal("revocation setup", err)
	}
	// The separate original grant is intentionally still active: verify a bad token.
	res, err := roundTrip(t, s, strings.Replace(req, token, strings.Repeat("1", 64), 1))
	if err == nil || res.OK || calls.Load() != 0 {
		t.Fatalf("bad token accepted: %+v %v", res, err)
	}
}
