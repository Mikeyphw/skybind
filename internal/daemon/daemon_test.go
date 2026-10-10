package daemon

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"skybind/internal/control"
	"skybind/internal/protocol"
	"testing"
	"time"
)

func TestSocketLockAndDispatch(t *testing.T) {
	d := filepath.Join(t.TempDir(), "private")
	if e := os.Mkdir(d, 0700); e != nil {
		t.Fatal(e)
	}
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
