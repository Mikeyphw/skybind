// Package brokeripc implements a bounded, read-only, UNIX peer-credential
// authenticated R1 transport. No production socket is opened by this package.
// A trusted Android/process verifier and explicit grant issuer must be wired
// before any cross-UID listener may be enabled.
package brokeripc

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"net"
	"syscall"
	"time"

	"skybind/internal/brokergrant"
)

const (
	MaxRequestBytes  = 16 * 1024
	MaxResponseBytes = 1024 * 1024
	ProtocolVersion  = 1
)

// KernelPeer is read from SO_PEERCRED, not from untrusted JSON fields.
type KernelPeer struct {
	UID uint32
	GID uint32
	PID int32
}

// Verifier must independently bind UID/PID to a trusted process identity,
// e.g. an Android package signing lineage and PID start-time. Never derive
// ProcessKey from a caller-provided field, UID alone, or /proc/cmdline alone.
type Verifier interface {
	VerifyPeer(KernelPeer) (brokergrant.Identity, error)
}

type Request struct {
	Version   int    `json:"version"`
	Token     string `json:"token"`
	Operation string `json:"operation"`
	Remote    string `json:"remote"`
	Path      string `json:"path"`
}

type Response struct {
	Version int             `json:"version"`
	OK      bool            `json:"ok"`
	Error   string          `json:"error,omitempty"`
	Result  json.RawMessage `json:"result,omitempty"`
}

// Reader receives only requests already checked against the authenticated
// grant. Implementations must use typed read-only backends, never a shell.
type Reader func(Request) (json.RawMessage, error)

type Server struct {
	Grants   *brokergrant.Store
	Verifier Verifier
	Read     Reader
	Timeout  time.Duration
}

func kernelPeer(c *net.UnixConn) (KernelPeer, error) {
	raw, err := c.SyscallConn()
	if err != nil {
		return KernelPeer{}, err
	}
	var peer *syscall.Ucred
	var sockErr error
	if err := raw.Control(func(fd uintptr) {
		peer, sockErr = syscall.GetsockoptUcred(int(fd), syscall.SOL_SOCKET, syscall.SO_PEERCRED)
	}); err != nil {
		return KernelPeer{}, err
	}
	if sockErr != nil {
		return KernelPeer{}, sockErr
	}
	if peer == nil || peer.Pid <= 0 {
		return KernelPeer{}, errors.New("peer_unavailable")
	}
	return KernelPeer{UID: peer.Uid, GID: peer.Gid, PID: peer.Pid}, nil
}

// rejectDuplicateRequestFields prevents ambiguous JSON key shadowing. A caller
// must never have two interpretations of the same token, scope, or operation.
func rejectDuplicateRequestFields(data []byte) error {
	d := json.NewDecoder(bytes.NewReader(data))
	token, err := d.Token()
	if err != nil || token != json.Delim('{') {
		return errors.New("request_object_required")
	}
	seen := make(map[string]bool, 5)
	for d.More() {
		key, err := d.Token()
		if err != nil {
			return err
		}
		name, ok := key.(string)
		if !ok || seen[name] {
			return errors.New("duplicate_or_invalid_field")
		}
		seen[name] = true
		// Request has only scalar string and integer fields. No nested values.
		value, err := d.Token()
		if err != nil {
			return err
		}
		switch value.(type) {
		case string, float64, json.Number, bool, nil:
		default:
			return errors.New("non_scalar_field")
		}
	}
	token, err = d.Token()
	if err != nil || token != json.Delim('}') {
		return errors.New("invalid_request_object")
	}
	if _, err = d.Token(); err != io.EOF {
		return errors.New("trailing_data")
	}
	return nil
}

func parseRequest(data []byte) (Request, error) {
	var r Request
	if len(data) == 0 || len(data) > MaxRequestBytes {
		return r, errors.New("request_size")
	}
	if err := rejectDuplicateRequestFields(data); err != nil {
		return Request{}, err
	}
	d := json.NewDecoder(bytes.NewReader(data))
	d.DisallowUnknownFields()
	if err := d.Decode(&r); err != nil {
		return Request{}, err
	}
	if err := d.Decode(new(any)); err != io.EOF {
		return Request{}, errors.New("trailing_data")
	}
	if r.Version != ProtocolVersion {
		return Request{}, errors.New("version_mismatch")
	}
	return r, nil
}

func writeResponse(c *net.UnixConn, response Response) error {
	data, err := json.Marshal(response)
	if err != nil {
		return err
	}
	if len(data) > MaxResponseBytes {
		return errors.New("response_size")
	}
	data = append(data, '\n')
	_, err = c.Write(data)
	return err
}

// ServeConn handles exactly one request on an already accepted Unix socket.
// The caller owns listener lifecycle and must never make this available until
// a production-grade Verifier and grant issuing control-plane are reviewed.
func (s *Server) ServeConn(c *net.UnixConn) error {
	if c == nil {
		return errors.New("nil_connection")
	}
	defer c.Close()
	denied := Response{Version: ProtocolVersion, OK: false, Error: "not_authorized"}
	if s == nil || s.Grants == nil || s.Verifier == nil || s.Read == nil {
		_ = writeResponse(c, denied)
		return errors.New("broker_not_configured")
	}
	timeout := s.Timeout
	if timeout <= 0 || timeout > 30*time.Second {
		timeout = 5 * time.Second
	}
	if err := c.SetDeadline(time.Now().Add(timeout)); err != nil {
		return err
	}
	kernel, err := kernelPeer(c)
	if err != nil {
		_ = writeResponse(c, denied)
		return errors.New("peer_not_verified")
	}
	verified, err := s.Verifier.VerifyPeer(kernel)
	if err != nil || verified.UID != kernel.UID || verified.ProcessKey == "" {
		_ = writeResponse(c, denied)
		return errors.New("peer_not_verified")
	}
	raw, err := io.ReadAll(io.LimitReader(c, MaxRequestBytes+1))
	if err != nil {
		_ = writeResponse(c, denied)
		return errors.New("bad_request")
	}
	request, err := parseRequest(raw)
	if err != nil {
		_ = writeResponse(c, denied)
		return errors.New("bad_request")
	}
	// Re-verify after bounded request parsing so a killed/reused PID cannot
	// retain a valid lease between connection acceptance and operation.
	current, identityErr := s.Verifier.VerifyPeer(kernel)
	if identityErr != nil || current != verified || current.UID != kernel.UID {
		_ = writeResponse(c, denied)
		return errors.New("peer_identity_changed")
	}
	if s.Grants.Authorize(request.Token, current, request.Operation, request.Remote, request.Path) != nil {
		_ = writeResponse(c, denied)
		return errors.New("not_authorized")
	}
	// Final check after grant authorization, immediately before invoking a
	// backend. A PID / signing transition must not survive an authorized token.
	last, identityErr := s.Verifier.VerifyPeer(kernel)
	if identityErr != nil || last != verified || last.UID != kernel.UID {
		_ = writeResponse(c, denied)
		return errors.New("peer_identity_changed_before_read")
	}
	result, err := s.Read(request)
	if err != nil {
		_ = writeResponse(c, Response{Version: ProtocolVersion, Error: "read_failed"})
		return errors.New("read_failed")
	}
	if !json.Valid(result) || len(result) > MaxResponseBytes-96 {
		_ = writeResponse(c, Response{Version: ProtocolVersion, Error: "invalid_backend_response"})
		return errors.New("invalid_backend_response")
	}
	return writeResponse(c, Response{Version: ProtocolVersion, OK: true, Result: result})
}

// PeerCredentials derives identity only from the local kernel, not from a
// request or an Android process name. Intended for the explicit grant handoff.
func PeerCredentials(c *net.UnixConn) (KernelPeer, error) { return kernelPeer(c) }
