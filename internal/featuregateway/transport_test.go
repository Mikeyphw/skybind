package featuregateway

import (
	"context"
	"encoding/json"
	"net"
	"os"
	"strings"
	"testing"
	"time"

	"skybind/internal/protocol"
)

func TestAPI04TransportRequiresExplicitRootGuardAndDispatcher(t *testing.T) {
	if err := (&EndpointServer{}).Start(); err == nil {
		t.Fatal("started unapproved gateway")
	}
	s := &EndpointServer{ExplicitlyEnabled: true}
	if err := s.Start(); err == nil {
		t.Fatal("started gateway without trusted guard")
	}
}
func TestAPI04ProtocolResponseShape(t *testing.T) {
	result := json.RawMessage(`{"state":"ok"}`)
	reply := Reply{Version: 1, RequestID: "request-1", OK: true, Result: result}
	raw, err := json.Marshal(reply)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(raw), `"request_id":"request-1"`) || !strings.Contains(string(raw), `"state":"ok"`) {
		t.Fatal("unexpected response")
	}
	if Endpoint != "\x00skybind-api04-bkx-query-v1" {
		t.Fatal("changed endpoint")
	}
}
func TestAPI04TransportDeniedWithoutBKXPeerIdentity(t *testing.T) {
	if os.Geteuid() != 0 {
		t.Skip("root-only listener fixture")
	}
	policy := samplePolicy()
	// Fixture peer UID differs from the operator-approved BKX app UID.
	guard, err := NewGuard(policy, Dependencies{Packages: pmFixture{ok: true}, Proc: procFixture{pid: 1, uid: policy.BKX.UID, label: policy.BKX.SELinuxContext, start: 22}})
	if err != nil {
		t.Fatal(err)
	}
	invoked := false
	server := &EndpointServer{Guard: guard, ExplicitlyEnabled: true, Dispatch: func(context.Context, protocol.Request) (protocol.Response, error) {
		invoked = true
		return protocol.Response{}, nil
	}}
	const name = "\x00skybind-api04-test-negative-v1"
	if err = server.startAt(name); err != nil {
		t.Fatal(err)
	}
	defer server.Close()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	done := make(chan error, 1)
	go func() { done <- server.Serve(ctx) }()
	c, err := net.DialTimeout("unix", name, time.Second)
	if err != nil {
		t.Fatal(err)
	}
	_ = c.SetDeadline(time.Now().Add(time.Second))
	_, _ = c.Write([]byte(`{"api_version":1,"request_id":"good","operation":"mount.status","arguments":{"name":"safeMount"}}`))
	if uc, ok := c.(*net.UnixConn); ok {
		_ = uc.CloseWrite()
	}
	var answer Reply
	if err = json.NewDecoder(c).Decode(&answer); err != nil {
		t.Fatal(err)
	}
	_ = c.Close()
	if answer.OK || answer.Error != "api04_peer_denied" || invoked {
		t.Fatalf("unauthorized peer dispatched: %+v", answer)
	}
	cancel()
	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("shutdown hung")
	}
}
