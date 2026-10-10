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
	"skybind/internal/rc"
	"testing"
)

type jobFixture struct{}

func (jobFixture) Execute(context.Context, jobs.Job) error { return nil }

type providerFixture struct{}

func (providerFixture) Run(context.Context, []byte, ...string) ([]byte, error) {
	return []byte("[]"), nil
}
func TestC03CatalogAndRequestBoundary(t *testing.T) {
	root := t.TempDir()
	for _, p := range []string{"jobs", "config", "rc"} {
		if e := os.Mkdir(filepath.Join(root, p), 0700); e != nil {
			t.Fatal(e)
		}
	}
	j, e := jobs.Open(filepath.Join(root, "jobs"), jobFixture{}, func() policy.Facts { return policy.Facts{Network: policy.Unknown} })
	if e != nil {
		t.Fatal(e)
	}
	p := provider.New(filepath.Join(root, "config"), providerFixture{})
	metrics := rc.New(filepath.Join(root, "rc"), func(string) bool { return false })
	engine := EngineWithServices(nil, nil, nil, nil, nil, nil, nil, nil, j, p, metrics)
	required := map[string]protocol.Class{"jobs.snapshot": protocol.Query, "jobs.preview": protocol.Preview, "jobs.apply": protocol.Run, "jobs.status": protocol.Query, "job.run.preview": protocol.Preview, "job.run": protocol.Run, "provider.status": protocol.Query, "provider.remotes": protocol.Query, "provider.browse": protocol.Query, "provider.crypt.password.set": protocol.Run, "provider.crypt.password.status": protocol.Query, "provider.crypt.recovery.status": protocol.Query, "provider.crypt.preview": protocol.Preview, "provider.crypt.create": protocol.Run, "rc.metrics": protocol.Query}
	for _, op := range engine.Descriptors() {
		if class, ok := required[op.Operation]; ok {
			if op.Class != class {
				t.Fatal("wrong C03 operation class", op.Operation)
			}
			delete(required, op.Operation)
		}
	}
	if len(required) > 0 {
		t.Fatalf("missing C03 operations: %v", required)
	}
	run := func(op string, class protocol.Class, args string) protocol.Response {
		return engine.Dispatch(context.Background(), protocol.Request{SchemaVersion: protocol.Version, RequestID: "c03", Operation: op, Class: class, Arguments: json.RawMessage(args)})
	}
	if !run("jobs.snapshot", protocol.Query, `{}`).OK {
		t.Fatal("jobs snapshot broken")
	}
	if run("provider.browse", protocol.Query, `{"remote":"cloud:../etc"}`).OK {
		t.Fatal("unsafe browse permitted")
	}
	if run("provider.crypt.password.set", protocol.Run, `{"password":"abcd","shell":"sh"}`).OK {
		t.Fatal("arbitrary input accepted")
	}
	if run("rc.metrics", protocol.Query, `{"name":"other"}`).OK {
		t.Fatal("unowned RC accepted")
	}
	if run("jobs.apply", protocol.Query, `{}`).OK {
		t.Fatal("wrong operation class")
	}
}
