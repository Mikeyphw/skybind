// Package daemon implements one privileged Unix-socket RPC owner.
package daemon

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"os"
	"path/filepath"
	"skybind/internal/control"
	"skybind/internal/protocol"
	"syscall"
	"time"
)

// Linux and Android sockaddr_un.sun_path is 108 bytes including the NUL.
const maxUnixSocketPath = 107

type Server struct {
	socket   string
	lock     string
	eng      *control.Engine
	listener net.Listener
	lockFD   *os.File
}

func New(socket string, engine *control.Engine) *Server {
	return &Server{socket: socket, lock: socket + ".lock", eng: engine}
}
func (s *Server) Start() error {
	if len(s.socket) > maxUnixSocketPath {
		return fmt.Errorf("unix socket path too long: %d bytes (maximum %d)", len(s.socket), maxUnixSocketPath)
	}
	if s.eng == nil {
		return errors.New("missing engine")
	}
	// Only an already verified private directory may contain these handles.
	d := filepath.Dir(s.socket)
	st, e := os.Lstat(d)
	if e != nil {
		return e
	}
	if !st.IsDir() || st.Mode().Perm() != 0700 || st.Mode()&os.ModeSymlink != 0 {
		return errors.New("unsafe socket directory")
	}
	f, e := os.OpenFile(s.lock, os.O_CREATE|os.O_RDWR, 0600)
	if e != nil {
		return e
	}
	if e = syscall.Flock(int(f.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); e != nil {
		f.Close()
		return errors.New("daemon already owns lock")
	}
	old, e := os.Lstat(s.socket)
	if e == nil {
		if old.Mode()&os.ModeSocket == 0 {
			f.Close()
			return errors.New("occupied socket path is not a socket")
		}
		// A stale socket is removable only while holding our exclusive instance lock.
		if e = os.Remove(s.socket); e != nil {
			f.Close()
			return e
		}
	} else if !os.IsNotExist(e) {
		f.Close()
		return e
	}
	l, e := net.Listen("unix", s.socket)
	if e != nil {
		f.Close()
		return e
	}
	if e = os.Chmod(s.socket, 0600); e != nil {
		l.Close()
		f.Close()
		return e
	}
	s.listener = l
	s.lockFD = f
	return nil
}
func (s *Server) Serve(ctx context.Context) error {
	if s.listener == nil {
		return errors.New("server not started")
	}
	go func() { <-ctx.Done(); s.listener.Close() }()
	for {
		conn, err := s.listener.Accept()
		if err != nil {
			if ctx.Err() != nil {
				return nil
			}
			return err
		}
		go s.handle(conn)
	}
}
func (s *Server) handle(c net.Conn) {
	defer c.Close()
	_ = c.SetDeadline(time.Now().Add(15 * time.Second))
	u, ok := c.(*net.UnixConn)
	if !ok {
		return
	}
	raw, e := u.SyscallConn()
	if e != nil {
		return
	}
	var peer *syscall.Ucred
	err := raw.Control(func(fd uintptr) { peer, e = syscall.GetsockoptUcred(int(fd), syscall.SOL_SOCKET, syscall.SO_PEERCRED) })
	if err != nil || e != nil || peer == nil || peer.Uid != uint32(os.Geteuid()) {
		return
	}
	req, e := protocol.Decode(c)
	var response protocol.Response
	if e != nil {
		response = protocol.Fail(req.RequestID, "invalid_envelope", "protocol", "decode", false)
	} else {
		response = s.eng.Dispatch(context.Background(), req)
	}
	data, e := protocol.MarshalResponse(response)
	if e != nil {
		data, _ = protocol.MarshalResponse(protocol.Fail(req.RequestID, "response_limit", "protocol", "encode", false))
	}
	_, _ = c.Write(data)
}
func (s *Server) Close() error {
	if s.listener != nil {
		_ = s.listener.Close()
	}
	if s.lockFD == nil {
		return nil
	}
	_ = os.Remove(s.socket)
	_ = syscall.Flock(int(s.lockFD.Fd()), syscall.LOCK_UN)
	e := s.lockFD.Close()
	s.lockFD = nil
	return e
}
func Call(ctx context.Context, path string, req protocol.Request) (protocol.Response, error) {
	d := net.Dialer{Timeout: 5 * time.Second}
	c, e := d.DialContext(ctx, "unix", path)
	if e != nil {
		return protocol.Response{}, e
	}
	defer c.Close()
	_ = c.SetDeadline(time.Now().Add(15 * time.Second))
	b, e := json.Marshal(req)
	if e != nil {
		return protocol.Response{}, e
	}
	if len(b) > protocol.MaxEnvelope {
		return protocol.Response{}, errors.New("oversize client request")
	}
	if _, e = c.Write(b); e != nil {
		return protocol.Response{}, e
	}
	if u, ok := c.(*net.UnixConn); ok {
		_ = u.CloseWrite()
	}
	buf, e := io.ReadAll(io.LimitReader(c, protocol.MaxResponse+2))
	if e != nil {
		return protocol.Response{}, e
	}
	if len(buf) > protocol.MaxResponse+1 {
		return protocol.Response{}, errors.New("oversize response")
	}
	var res protocol.Response
	if e = protocol.StrictBytes(buf, &res); e != nil {
		return res, fmt.Errorf("invalid response: %w", e)
	}
	if res.SchemaVersion != protocol.Version || res.RequestID != req.RequestID {
		return res, errors.New("mismatched response identity")
	}
	return res, nil
}
