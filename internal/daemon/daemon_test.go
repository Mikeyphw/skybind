package daemon

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"skybind/internal/control"
	"skybind/internal/protocol"
	"strings"
	"testing"
	"time"
)

func TestSocketLockAndDispatch(t *testing.T) {
	// Devtool and Android can set TMPDIR to a path too long for AF_UNIX.
	// Create a randomly named private directory under a short, writable root;
	// the socket itself is still a pathname socket with all normal ownership
	// and single-instance checks intact.
	d := shortSocketTestDir(t)
	eng := control.New()
	eng.Register("runtime.status", protocol.Query, func(context.Context, json.RawMessage) (any, error) { return map[string]bool{"ready": false}, nil })
	sock := filepath.Join(d, "daemon.sock")
	a := New(sock, eng)
	if e := a.Start(); e != nil {
		t.Fatal(e)
	}
	defer a.Close()
	b := New(sock, eng)
	if e := b.Start(); e == nil {
		t.Fatal("two daemons acquired lock")
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go a.Serve(ctx)
	deadline := time.Now().Add(time.Second)
	var res protocol.Response
	var err error
	for time.Now().Before(deadline) {
		res, err = Call(context.Background(), sock, protocol.Request{SchemaVersion: 1, RequestID: "x", Operation: "runtime.status", Class: protocol.Query})
		if err == nil {
			break
		}
		time.Sleep(time.Millisecond * 5)
	}
	if err != nil || !res.OK {
		t.Fatalf("rpc %v: %#v", err, res)
	}
	bad, e := Call(context.Background(), sock, protocol.Request{SchemaVersion: 1, RequestID: "y", Operation: "shell.exec", Class: protocol.Run})
	if e != nil || bad.OK {
		t.Fatal("unknown operation not rejected")
	}
}

// shortSocketTestDir avoids nesting a pathname Unix socket under t.TempDir():
// test-runner paths may already consume the kernel's 107-byte socket limit.
// A fresh random directory is owned by this test and removed via Cleanup.
func shortSocketTestDir(t *testing.T) string {
	t.Helper()
	var candidates []string
	if prefix := os.Getenv("PREFIX"); prefix != "" {
		candidates = append(candidates, filepath.Join(prefix, "tmp"))
	}
	if home, err := os.UserHomeDir(); err == nil {
		candidates = append(candidates, home)
	}
	candidates = append(candidates, "/tmp", os.TempDir())
	for _, root := range candidates {
		if !filepath.IsAbs(root) || len(filepath.Join(root, "sb-XXXXXXXX", "daemon.sock")) > maxUnixSocketPath {
			continue
		}
		dir, err := os.MkdirTemp(root, "sb-")
		if err != nil {
			continue
		}
		if len(filepath.Join(dir, "daemon.sock")) > maxUnixSocketPath {
			_ = os.RemoveAll(dir)
			continue
		}
		t.Cleanup(func() {
			if err := os.RemoveAll(dir); err != nil {
				t.Errorf("clean socket test directory: %v", err)
			}
		})
		return dir
	}
	t.Fatal("no writable short directory for Linux/Android pathname Unix socket tests")
	return ""
}

func TestOverlongSocketPathFailsBeforeLockCreation(t *testing.T) {
	d := shortSocketTestDir(t)
	socket := filepath.Join(d, strings.Repeat("s", maxUnixSocketPath)+".sock")
	s := New(socket, control.New())
	err := s.Start()
	if err == nil || !strings.Contains(err.Error(), "socket path too long") {
		t.Fatalf("expected explicit socket-length error, got %v", err)
	}
	if _, err := os.Lstat(socket + ".lock"); !os.IsNotExist(err) {
		t.Fatalf("oversize socket should not create lock; stat error=%v", err)
	}
}
