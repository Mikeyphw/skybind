package featuregateway

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net"
	"os"
	"skybind/internal/protocol"
	"sync"
	"time"
)

// MutationEndpointServer listens on a SEPARATE abstract endpoint. P2's
// EndpointServer remains read-only and cannot execute a mutation by policy.
type MutationEndpointServer struct {
	Service           *MutationService
	ExplicitlyEnabled bool
	mu                sync.Mutex
	listener          *net.UnixListener
}

func (s *MutationEndpointServer) Start() error { return s.startAt(mutationEndpoint) }
func (s *MutationEndpointServer) startAt(endpoint string) error {
	if s == nil || os.Geteuid() != 0 || !s.ExplicitlyEnabled || s.Service == nil || s.Service.Guard == nil || s.Service.Store == nil ||
		endpoint == "" || len(endpoint) >= 108 || endpoint[0] != 0 {
		return errors.New("api04_mutation_socket_denied")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.listener != nil {
		return errors.New("api04_mutation_already_started")
	}
	l, e := net.ListenUnix("unix", &net.UnixAddr{Name: endpoint, Net: "unix"})
	if e != nil {
		return e
	}
	s.listener = l
	return nil
}
func (s *MutationEndpointServer) Close() error {
	if s == nil {
		return nil
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.listener == nil {
		return nil
	}
	e := s.listener.Close()
	s.listener = nil
	return e
}
func (s *MutationEndpointServer) handle(ctx context.Context, c *net.UnixConn) {
	defer c.Close()
	_ = c.SetDeadline(time.Now().Add(12 * time.Second))
	deny := func(code string) { sendReply(c, Reply{Version: 1, OK: false, Error: code}) }
	peer, e := kernelPeer(c)
	if e != nil || peer.UID != s.Service.Guard.policy.BKX.UID {
		deny("api04_mutation_peer_denied")
		return
	}
	body, e := io.ReadAll(io.LimitReader(c, protocol.MaxEnvelope+1))
	if e != nil || len(body) == 0 || len(body) > protocol.MaxEnvelope {
		deny("api04_mutation_request_invalid")
		return
	}
	before, e := s.Service.verify(peer)
	if e != nil {
		deny("api04_mutation_identity_denied")
		return
	}
	call, e := DecodeMutationCall(body)
	if e != nil {
		deny("api04_mutation_request_invalid")
		return
	}
	execution, cancel := context.WithTimeout(ctx, 8*time.Second)
	defer cancel()
	result, e := s.Service.Process(execution, peer, call)
	if e != nil {
		deny("api04_mutation_denied")
		return
	}
	// A PID restart or different signer must not receive any prior result.
	after, e := s.Service.verify(peer)
	if e != nil || after != before {
		deny("api04_mutation_identity_changed")
		return
	}
	raw, e := json.Marshal(result)
	if e != nil || len(raw) > MaxReplyBytes {
		deny("api04_mutation_response_unavailable")
		return
	}
	sendReply(c, Reply{Version: 1, RequestID: result.RequestID, OK: true, Result: raw})
}
func (s *MutationEndpointServer) Serve(ctx context.Context) error {
	if s == nil || ctx == nil {
		return errors.New("api04_mutation_not_started")
	}
	s.mu.Lock()
	l := s.listener
	s.mu.Unlock()
	if l == nil {
		return errors.New("api04_mutation_not_started")
	}
	stopped := make(chan struct{})
	go func() {
		select {
		case <-ctx.Done():
			_ = l.Close()
		case <-stopped:
		}
	}()
	defer close(stopped)
	sem := make(chan struct{}, 8)
	var wg sync.WaitGroup
	defer wg.Wait()
	for {
		c, e := l.AcceptUnix()
		if e != nil {
			if ctx.Err() != nil {
				return nil
			}
			return e
		}
		select {
		case sem <- struct{}{}:
			wg.Add(1)
			go func(c *net.UnixConn) { defer wg.Done(); defer func() { <-sem }(); s.handle(ctx, c) }(c)
		default:
			_ = c.Close()
		}
	}
}
