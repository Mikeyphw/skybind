package brokeripc

import (
	"context"
	"encoding/json"
	"errors"
	"net"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"skybind/internal/brokergrant"
)

type localVerifier struct {
	identity brokergrant.Identity
	reject   bool
}

func (v localVerifier) VerifyPeer(p KernelPeer) (brokergrant.Identity, error) {
	if v.reject || p.UID != v.identity.UID {
		return brokergrant.Identity{}, errors.New("denied")
	}
	return v.identity, nil
}
func TestConsumerSocketDefaultDeniedAndScopedRequest(t *testing.T) {
	if os.Geteuid() != 0 {
		t.Skip("requires root-owned socket fixture")
	}
	state := filepath.Join(t.TempDir(), "state")
	if e := os.Mkdir(state, 0700); e != nil {
		t.Fatal(e)
	}
	identity := brokergrant.Identity{UID: 0, ProcessKey: "approved-chrootctl-pid"}
	grants := brokergrant.New()
	var called int
	s := &ConsumerSocket{Directory: filepath.Join(state, "consumer-gateway"), BKXUID: 10327, Grants: grants, Verifier: localVerifier{identity: identity}, Backend: func(r Request) (json.RawMessage, error) { called++; return json.RawMessage(`{"value":true}`), nil }}
	if s.startAt(state) == nil {
		t.Fatal("default listener started without authorization")
	}
	s.ExplicitlyEnabled = true
	if s.Start() == nil {
		t.Fatal("non-canonical public listener started")
	}
	if e := s.startAt(state); e != nil {
		t.Fatal(e)
	}
	defer s.Close()
	socket := filepath.Join(s.Directory, "consumer.sock")
	if st, e := os.Lstat(socket); e != nil || st.Mode().Perm() != 0660 {
		t.Fatal("unsafe socket", e)
	}
	if st, e := os.Lstat(s.Directory); e != nil || st.Mode().Perm() != 0710 {
		t.Fatal("unsafe directory", e)
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	done := make(chan error, 1)
	go func() { done <- s.Serve(ctx) }()
	query := func(token string) Response {
		t.Helper()
		conn, e := net.DialTimeout("unix", socket, time.Second)
		if e != nil {
			t.Fatal(e)
		}
		defer conn.Close()
		req := `{"version":1,"token":"` + token + `","operation":"rclone.version","remote":"drive","path":""}`
		if _, e = conn.Write([]byte(req)); e != nil {
			t.Fatal(e)
		}
		if e = conn.(*net.UnixConn).CloseWrite(); e != nil {
			t.Fatal(e)
		}
		var out Response
		if e = json.NewDecoder(conn).Decode(&out); e != nil {
			t.Fatal(e)
		}
		return out
	}
	if got := query(strings.Repeat("0", 64)); got.OK || called != 0 {
		t.Fatal("missing grant leaked data")
	}
	token, rec, e := grants.Issue(brokergrant.GrantSpec{Caller: identity, Remote: "drive", Operations: []string{"rclone.version"}, TTL: time.Minute})
	if e != nil {
		t.Fatal(e)
	}
	if got := query(token); !got.OK || called != 1 {
		t.Fatal("owned read-only grant rejected", got)
	}
	if !grants.Revoke(rec.ID) {
		t.Fatal("revocation failed")
	}
	if got := query(token); got.OK || called != 1 {
		t.Fatal("revoked grant reached backend")
	}
	cancel()
	if e = <-done; e != nil {
		t.Fatal(e)
	}
	if e = s.Close(); e != nil && !errors.Is(e, net.ErrClosed) {
		t.Fatal(e)
	}
	if _, e = os.Lstat(socket); !os.IsNotExist(e) {
		t.Fatal("socket not removed")
	}
}
