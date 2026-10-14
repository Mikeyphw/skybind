package daemon

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"skybind/internal/jobs"
	"skybind/internal/mounts/policy"
	"skybind/internal/protocol"
	"skybind/internal/provider"
	"testing"
)

type b1StatRunner struct{}

func (b1StatRunner) Run(context.Context, []byte, ...string) ([]byte, error) {
	return []byte(`{"Path":"a","Name":"a","Size":12,"IsDir":false}`), nil
}

type b1Exec struct{ run chan jobs.Job }

func (e b1Exec) Execute(ctx context.Context, j jobs.Job) error { e.run <- j; return nil }
func TestB1RPCMountlessTransferBoundary(t *testing.T) {
	root := t.TempDir()
	for _, d := range []string{"jobs", "provider"} {
		dir := filepath.Join(root, d)
		if err := os.Mkdir(dir, 0700); err != nil {
			t.Fatal(err)
		}
	}
	conf := filepath.Join(root, "provider", "rclone.conf")
	if err := os.WriteFile(conf, []byte("[alpha]\ntype=drive\n[beta]\ntype=crypt\nremote=alpha:archive\n"), 0600); err != nil {
		t.Fatal(err)
	}
	exec := b1Exec{make(chan jobs.Job, 4)}
	s, err := jobs.Open(filepath.Join(root, "jobs"), exec, func() policy.Facts { return policy.Facts{Network: policy.WiFi} })
	if err != nil {
		t.Fatal(err)
	}
	p := provider.New(filepath.Join(root, "provider"), b1StatRunner{})
	engine := EngineWithServices(nil, nil, nil, nil, nil, nil, nil, nil, s, p, nil)
	rpc := func(name string, cls protocol.Class, args string) protocol.Response {
		return engine.Dispatch(context.Background(), protocol.Request{SchemaVersion: 1, RequestID: "b1-test", Operation: name, Class: cls, Arguments: json.RawMessage(args)})
	}
	if !rpc("remote.stat", protocol.Query, `{"endpoint":"alpha:a"}`).OK {
		t.Fatal("stat RPC failed")
	}
	if rpc("remote.stat", protocol.Query, `{"endpoint":"unknown:a"}`).OK {
		t.Fatal("unknown remote disclosed")
	}
	if rpc("remote.transfer.preview", protocol.Preview, `{"kind":"sync","source":"alpha:a","destination":"beta:b"}`).OK {
		t.Fatal("sync allowed")
	}
	if rpc("remote.transfer.preview", protocol.Preview, `{"kind":"copy","source":"alpha:a","destination":"unknown:b"}`).OK {
		t.Fatal("unconfigured remote accepted")
	}
	preview := rpc("remote.transfer.preview", protocol.Preview, `{"kind":"copy","source":"alpha:a","destination":"beta:b"}`)
	if !preview.OK {
		t.Fatalf("preview RPC failed %+v", preview.Error)
	}
	var tok string
	if result, ok := preview.Result.(map[string]any); ok {
		tok, _ = result["proof"].(string)
	}
	if len(tok) != 64 {
		t.Fatal("preview lacks proof")
	}
	// Changing the remote configuration must invalidate the old proof.
	if err := os.WriteFile(conf, []byte("[alpha]\ntype=drive\ntoken=changed\n[beta]\ntype=crypt\nremote=alpha:archive\n"), 0600); err != nil {
		t.Fatal(err)
	}
	if rpc("remote.transfer.start", protocol.Run, `{"kind":"copy","source":"alpha:a","destination":"beta:b","proof":"`+tok+`"}`).OK {
		t.Fatal("stale configuration proof accepted")
	}
	preview = rpc("remote.transfer.preview", protocol.Preview, `{"kind":"copy","source":"alpha:a","destination":"beta:b"}`)
	if !preview.OK {
		t.Fatal(preview.Error)
	}
	tok = preview.Result.(map[string]any)["proof"].(string)
	response := rpc("remote.transfer.start", protocol.Run, `{"kind":"copy","source":"alpha:a","destination":"beta:b","proof":"`+tok+`"}`)
	if !response.OK {
		t.Fatalf("start failed %+v", response.Error)
	}
	j := <-exec.run
	if !j.IgnoreExisting {
		t.Fatal("overwrites permitted")
	}
	if rpc("remote.transfer.start", protocol.Run, `{"kind":"copy","source":"alpha:a","destination":"beta:b","proof":"`+tok+`"}`).OK {
		t.Fatal("proof replayed")
	}
}
