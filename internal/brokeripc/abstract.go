package brokeripc

// This explicitly activated abstract Unix listener is an R1 consumer-transport
// candidate. It does not modify the ordinary Skybind daemon or issue grants.
// An abstract socket has no filesystem ancestors, so a pinned Android UID
// does not have to traverse the root-owned /data/adb/skybind state directory.
// Every accepted connection is independently checked by Server.ServeConn via
// SO_PEERCRED, the platform/module verifier and a process-bound grant.

import (
	"context"
	"errors"
	"net"
	"os"
	"sync"
	"time"

	"skybind/internal/brokergrant"
)

const ConsumerAbstractEndpoint = "\x00skybind-r1-consumer-gateway-v1"
const maxAbstractConsumers = 8

type AbstractConsumerSocket struct {
	BKXUID            uint32
	ExplicitlyEnabled bool
	Grants            *brokergrant.Store
	Verifier          Verifier
	Backend           Reader

	mu       sync.Mutex
	listener *net.UnixListener
}

// Start may only be called by an explicitly authorized root-owned gateway
// process; it is never called by any Skybind module startup/service hook.
// The canonical abstract socket name is not selected by a consumer or policy.
func (s *AbstractConsumerSocket) Start() error {
	return s.startAt(ConsumerAbstractEndpoint)
}

// startAt exists only for isolated same-package transport tests. Runtime code
// MUST use Start(), which never accepts a caller-selected socket destination.
func (s *AbstractConsumerSocket) startAt(endpoint string) error {
	if s == nil || os.Geteuid() != 0 || !s.ExplicitlyEnabled || s.BKXUID < 10000 ||
		s.Grants == nil || s.Verifier == nil || s.Backend == nil ||
		len(endpoint) < 3 || len(endpoint) >= 108 || endpoint[0] != 0 {
		return errors.New("r1_abstract_consumer_gateway_not_authorized")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.listener != nil {
		return errors.New("r1_consumer_gateway_already_started")
	}
	l, err := net.ListenUnix("unix", &net.UnixAddr{Name: endpoint, Net: "unix"})
	if err != nil {
		return err
	}
	s.listener = l
	return nil
}

func (s *AbstractConsumerSocket) Serve(ctx context.Context) error {
	if s == nil || ctx == nil {
		return errors.New("r1_gateway_not_started")
	}
	s.mu.Lock()
	l := s.listener
	s.mu.Unlock()
	if l == nil {
		return errors.New("r1_gateway_not_started")
	}
	stop := make(chan struct{})
	go func() {
		select {
		case <-ctx.Done():
			_ = l.Close()
		case <-stop:
		}
	}()
	defer close(stop)
	sem := make(chan struct{}, maxAbstractConsumers)
	var active sync.WaitGroup
	defer active.Wait()
	server := Server{Grants: s.Grants, Verifier: s.Verifier, Read: s.Backend, Timeout: 5 * time.Second}
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
			active.Add(1)
			go func(conn *net.UnixConn) { defer active.Done(); defer func() { <-sem }(); _ = server.ServeConn(conn) }(c)
		default:
			// Admission pressure never bypasses identity checks or executes a
			// backend; excess connections are closed without receiving data.
			_ = c.Close()
		}
	}
}

func (s *AbstractConsumerSocket) Close() error {
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
