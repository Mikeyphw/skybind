//go:build linux || android

// Package networkwatch supplies untrusted OS link/route change *hints*.
// Decisions to start FUSE remain in the authenticated supervisor/policy path.
// This package holds no wake lock, polls no daemon, and never issues commands.
package networkwatch

import (
	"context"
	"errors"
	"syscall"
)

// Netlink multicast groups: links, address changes, IPv4/IPv6 routes.
const groups = 0x1 | 0x10 | 0x40 | 0x100 | 0x400

// Listen creates a bounded, coalescing kernel-event listener. No permission to
// receive kernel events is a supported condition; callers retain a timer fallback.
func Listen(ctx context.Context) (<-chan struct{}, error) {
	fd, err := syscall.Socket(syscall.AF_NETLINK, syscall.SOCK_RAW|syscall.SOCK_CLOEXEC, syscall.NETLINK_ROUTE)
	if err != nil {
		return nil, err
	}
	syscall.CloseOnExec(fd)
	if err = syscall.Bind(fd, &syscall.SockaddrNetlink{Family: syscall.AF_NETLINK, Groups: groups}); err != nil {
		syscall.Close(fd)
		return nil, err
	}
	// Bounded receive prevents an unkillable goroutine during graceful shutdown.
	if err = syscall.SetsockoptTimeval(fd, syscall.SOL_SOCKET, syscall.SO_RCVTIMEO, &syscall.Timeval{Sec: 1}); err != nil {
		syscall.Close(fd)
		return nil, err
	}
	out := make(chan struct{}, 1)
	go func() {
		defer close(out)
		defer syscall.Close(fd)
		buf := make([]byte, 8192)
		for ctx.Err() == nil {
			n, _, err := syscall.Recvfrom(fd, buf, 0)
			if err != nil {
				if errors.Is(err, syscall.EAGAIN) || errors.Is(err, syscall.EWOULDBLOCK) || errors.Is(err, syscall.EINTR) {
					continue
				}
				// Missed events must never disable the periodic fallback.
				if errors.Is(err, syscall.ENOBUFS) {
					notify(out)
					continue
				}
				return
			}
			if n > 0 {
				notify(out)
			}
		}
	}()
	return out, nil
}

func notify(out chan<- struct{}) {
	select {
	case out <- struct{}{}:
	default:
	}
}
