package featuregateway

// API-04 is an explicitly started, root-owned, cross-UID query endpoint. It
// never starts from Skybind's ordinary daemon or exposes the R1 grant store.
// Abstract Unix addressing avoids relying on traversal through /data/adb.
import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net"
	"os"
	"sync"
	"syscall"
	"time"

	"skybind/internal/brokeripc"
	"skybind/internal/protocol"
)

const Endpoint = "\x00skybind-api04-bkx-query-v1"
const MaxReplyBytes = protocol.MaxResponse
const maxConnections = 8

type Dispatch func(context.Context, protocol.Request) (protocol.Response, error)

type EndpointServer struct {
	Guard             *Guard
	Dispatch          Dispatch
	ExplicitlyEnabled bool
	mu                sync.Mutex
	listener          *net.UnixListener
}

func (s *EndpointServer) Start() error { return s.startAt(Endpoint) }

// startAt permits isolated test sockets. Production has no configurable name.
func (s *EndpointServer) startAt(name string) error {
	if s == nil || os.Geteuid() != 0 || !s.ExplicitlyEnabled || s.Guard == nil || s.Dispatch == nil ||
		len(name) < 3 || len(name) >= 108 || name[0] != 0 {
		return errors.New("api04_transport_not_authorized")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.listener != nil {
		return errors.New("api04_transport_already_started")
	}
	l, err := net.ListenUnix("unix", &net.UnixAddr{Name: name, Net: "unix"})
	if err != nil {
		return err
	}
	s.listener = l
	return nil
}

func kernelPeer(c *net.UnixConn) (brokeripc.KernelPeer, error) {
	raw, err := c.SyscallConn()
	if err != nil {
		return brokeripc.KernelPeer{}, err
	}
	var u *syscall.Ucred
	var sysErr error
	err = raw.Control(func(fd uintptr) {
		u, sysErr = syscall.GetsockoptUcred(int(fd), syscall.SOL_SOCKET, syscall.SO_PEERCRED)
	})
	if err != nil || sysErr != nil || u == nil || u.Pid <= 0 {
		return brokeripc.KernelPeer{}, errors.New("api04_peer_unavailable")
	}
	return brokeripc.KernelPeer{PID: u.Pid, UID: u.Uid, GID: u.Gid}, nil
}

type Reply struct {
	Version   int             `json:"version"`
	RequestID string          `json:"request_id,omitempty"`
	OK        bool            `json:"ok"`
	Result    json.RawMessage `json:"result,omitempty"`
	Error     string          `json:"error,omitempty"`
}

func sendReply(conn *net.UnixConn, r Reply) {
	data, err := json.Marshal(r)
	if err != nil || len(data) > MaxReplyBytes {
		data = []byte(`{"version":1,"ok":false,"error":"api04_response_unavailable"}`)
	}
	data = append(data, '\n')
	_, _ = conn.Write(data)
}

func (s *EndpointServer) handle(ctx context.Context, c *net.UnixConn) {
	defer c.Close()
	_ = c.SetDeadline(time.Now().Add(12 * time.Second))
	denied := func(code string) { sendReply(c, Reply{Version: 1, OK: false, Error: code}) }
	peer, err := kernelPeer(c)
	if err != nil || peer.UID != s.Guard.policy.BKX.UID {
		denied("api04_peer_denied")
		return
	}
	// The peer is authenticated by Guard.Prepare, not by caller-supplied JSON.
	// An API-04 request is one strict JSON envelope terminated by a write-half
	// close, matching Android LocalSocket.shutdownOutput.
	body, err := io.ReadAll(io.LimitReader(c, int64(protocol.MaxEnvelope)+1))
	if err != nil || len(body) == 0 || len(body) > protocol.MaxEnvelope {
		denied("api04_request_invalid")
		return
	}
	req, id, err := s.Guard.Prepare(peer, body)
	if err != nil || id.ProcessKey == "" {
		denied("api04_admission_denied")
		return
	}
	// No mutation operation can reach Dispatch: Guard.Prepare pins exact
	// mount, operation, principal and the query class.
	callCtx, cancel := context.WithTimeout(ctx, 8*time.Second)
	defer cancel()
	outer, err := s.Dispatch(callCtx, req)
	if err != nil || outer.SchemaVersion != protocol.Version || outer.RequestID != req.RequestID || !outer.OK {
		denied("api04_daemon_unavailable")
		return
	}
	raw, err := json.Marshal(outer.Result)
	if err != nil || len(raw) == 0 || len(raw) > MaxReplyBytes {
		denied("api04_daemon_reply_invalid")
		return
	}
	var inner protocol.Response
	if err = protocol.StrictBytes(raw, &inner); err != nil || inner.SchemaVersion != protocol.Version ||
		inner.RequestID != req.RequestID || !inner.OK {
		denied("api04_daemon_reply_denied")
		return
	}
	// Reattest the same kernel peer after remote dispatch to avoid returning
	// information on a PID-reused or re-signed process identity.
	again, err := s.Guard.verifier.VerifyPeer(peer)
	if err != nil || again != id {
		denied("api04_identity_changed")
		return
	}
	result, err := json.Marshal(inner.Result)
	if err != nil || len(result) > MaxReplyBytes || !json.Valid(result) || bytes.Equal(result, []byte("null")) {
		denied("api04_result_invalid")
		return
	}
	sendReply(c, Reply{Version: 1, RequestID: req.RequestID, OK: true, Result: result})
}

func (s *EndpointServer) Serve(ctx context.Context) error {
	if s == nil || ctx == nil {
		return errors.New("api04_transport_not_started")
	}
	s.mu.Lock()
	l := s.listener
	s.mu.Unlock()
	if l == nil {
		return errors.New("api04_transport_not_started")
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
	sem := make(chan struct{}, maxConnections)
	var workers sync.WaitGroup
	defer workers.Wait()
	for {
		c, err := l.AcceptUnix()
		if err != nil {
			if ctx.Err() != nil {
				return nil
			}
			return err
		}
		select {
		case sem <- struct{}{}:
			workers.Add(1)
			go func(c *net.UnixConn) { defer workers.Done(); defer func() { <-sem }(); s.handle(ctx, c) }(c)
		default:
			_ = c.Close()
		}
	}
}
func (s *EndpointServer) Close() error {
	if s == nil {
		return nil
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.listener == nil {
		return nil
	}
	err := s.listener.Close()
	s.listener = nil
	return err
}
