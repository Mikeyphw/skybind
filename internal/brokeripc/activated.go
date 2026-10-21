package brokeripc

import (
	"context"
	"errors"
	"net"
	"os"
	"path/filepath"
	"syscall"
	"time"

	"skybind/internal/brokergrant"
)

// ConsumerSocket is a separate, explicitly activated listener. It is never
// started by the ordinary Skybind daemon. Only read-only typed requests reach
// Server.ServeConn, with SO_PEERCRED and per-request grant checks.
// Root:BKXUID 0710 directory + root:BKXUID 0660 socket lets that single Android
// app UID connect; other apps cannot traverse the directory. A root client must
// still authenticate via its sealed-module attestor and a separate grant.
type ConsumerSocket struct {
	Directory         string
	BKXUID            uint32
	ExplicitlyEnabled bool
	Grants            *brokergrant.Store
	Verifier          Verifier
	Backend           Reader
	listener          *net.UnixListener
	socketInfo        os.FileInfo
	createdDirectory  bool
}

func (s *ConsumerSocket) Start() error {
	return s.startAt("/data/adb/skybind")
}

// startAt is private: host tests may use a disposable root; exported Start never does.
func (s *ConsumerSocket) startAt(parent string) error {
	if s == nil || !s.ExplicitlyEnabled || os.Geteuid() != 0 || s.BKXUID < 10000 || s.Grants == nil || s.Verifier == nil || s.Backend == nil ||
		s.Directory != filepath.Join(parent, "consumer-gateway") {
		return errors.New("consumer_gateway_not_authorized")
	}
	// The canonical root-owned /data/adb/skybind directory is already verified
	// by paths.EnsurePrivateState in a separate privileged startup.
	root, err := os.Lstat(parent)
	if err != nil || !root.IsDir() || root.Mode().Perm() != 0700 || root.Mode()&os.ModeSymlink != 0 {
		return errors.New("unsafe_gateway_parent")
	}
	if st, ok := root.Sys().(*syscall.Stat_t); !ok || st.Uid != 0 {
		return errors.New("unsafe_gateway_parent")
	}
	if err = os.Mkdir(s.Directory, 0700); err == nil {
		s.createdDirectory = true
	} else if !os.IsExist(err) {
		return err
	}
	cleanup := func() {
		if s.createdDirectory {
			_ = os.Remove(s.Directory)
			s.createdDirectory = false
		}
	}
	d, err := os.Lstat(s.Directory)
	if err != nil || !d.IsDir() || d.Mode()&os.ModeSymlink != 0 || d.Mode().Perm()&0022 != 0 {
		cleanup()
		return errors.New("unsafe_gateway_directory")
	}
	if st, ok := d.Sys().(*syscall.Stat_t); !ok || st.Uid != 0 || (d.Mode().Perm() != 0700 && d.Mode().Perm() != 0710) {
		cleanup()
		return errors.New("unsafe_gateway_directory")
	}
	socket := filepath.Join(s.Directory, "consumer.sock")
	if _, err = os.Lstat(socket); err == nil {
		cleanup()
		return errors.New("socket_already_exists")
	} else if !os.IsNotExist(err) {
		cleanup()
		return err
	}
	// While the directory remains 0700, connecting is inaccessible to apps.
	l, err := net.ListenUnix("unix", &net.UnixAddr{Name: socket, Net: "unix"})
	if err != nil {
		cleanup()
		return err
	}
	l.SetUnlinkOnClose(false)
	fail := func(e error) error { _ = l.Close(); _ = os.Remove(socket); cleanup(); return e }
	if err = os.Chown(socket, 0, int(s.BKXUID)); err != nil {
		return fail(err)
	}
	if err = os.Chmod(socket, 0660); err != nil {
		return fail(err)
	}
	if err = os.Chown(s.Directory, 0, int(s.BKXUID)); err != nil {
		return fail(err)
	}
	if err = os.Chmod(s.Directory, 0710); err != nil {
		return fail(err)
	}
	st, err := os.Lstat(socket)
	if err != nil || st.Mode()&os.ModeSocket == 0 || st.Mode().Perm() != 0660 {
		return fail(errors.New("unsafe_gateway_socket"))
	}
	if owner, ok := st.Sys().(*syscall.Stat_t); !ok || owner.Uid != 0 || owner.Gid != s.BKXUID {
		return fail(errors.New("unsafe_gateway_socket"))
	}
	s.listener = l
	s.socketInfo = st
	return nil
}

// Serve is bounded by context and a maximum of eight concurrent connections.
// No client request can control the listener location, backend, grant issuance,
// or choice of verifier.
func (s *ConsumerSocket) Serve(ctx context.Context) error {
	if s == nil || s.listener == nil {
		return errors.New("gateway_not_started")
	}
	done := make(chan struct{})
	go func() {
		select {
		case <-ctx.Done():
			_ = s.listener.Close()
		case <-done:
		}
	}()
	defer close(done)
	sem := make(chan struct{}, 8)
	srv := Server{Grants: s.Grants, Verifier: s.Verifier, Read: s.Backend, Timeout: 5 * time.Second}
	for {
		c, err := s.listener.AcceptUnix()
		if err != nil {
			if ctx.Err() != nil {
				return nil
			}
			return err
		}
		select {
		case sem <- struct{}{}:
			go func() { defer func() { <-sem }(); _ = srv.ServeConn(c) }()
		default:
			_ = c.Close()
		}
	}
}
func (s *ConsumerSocket) Close() error {
	if s == nil || s.listener == nil {
		return nil
	}
	e := s.listener.Close()
	s.listener = nil
	socket := filepath.Join(s.Directory, "consumer.sock")
	if st, err := os.Lstat(socket); err == nil && s.socketInfo != nil && os.SameFile(st, s.socketInfo) {
		_ = os.Remove(socket)
	}
	// Do not recursively remove the group-searchable directory or change its
	// permissions in ways that might affect another daemon instance.
	return e
}
