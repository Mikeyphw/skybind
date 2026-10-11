package daemon

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"skybind/internal/mounts/config"
	"skybind/internal/mounts/lifecycle"
	"skybind/internal/namespace"
	"skybind/internal/protocol"
	"skybind/internal/rootmgr"
	"testing"
)

type fakeRootStatus struct{}

func (fakeRootStatus) Status() (rootmgr.Status, error) {
	return rootmgr.Status{Manager: "unknown", DeviceQualified: false}, nil
}
func TestPlatformOperationCatalogAndStrictInputs(t *testing.T) {
	d := filepath.Join(t.TempDir(), "config")
	if e := os.Mkdir(d, 0700); e != nil {
		t.Fatal(e)
	}
	store, e := config.Open(d)
	if e != nil {
		t.Fatal(e)
	}
	mount := lifecycle.Canonical(store)
	ns := namespace.NewManager(mount, namespace.CanonicalScanner(), nil, filepath.Join(t.TempDir(), "ns"))
	eng := EngineWithPlatform(nil, store, mount, nil, nil, nil, ns, fakeRootStatus{})
	all := map[string]protocol.Class{}
	for _, v := range eng.Descriptors() {
		all[v.Operation] = v.Class
	}
	for op, cl := range map[string]protocol.Class{"namespace.inspect": protocol.Query, "namespace.preview": protocol.Preview, "namespace.apply": protocol.Run, "namespace.rollback.preview": protocol.Preview, "namespace.rollback": protocol.Run, "namespace.reconcile": protocol.Reconcile, "platform.status": protocol.Query} {
		if all[op] != cl {
			t.Fatalf("operation %s not registered correctly: %s", op, all[op])
		}
	}
	call := func(op string, cl protocol.Class, args string) protocol.Response {
		return eng.Dispatch(context.Background(), protocol.Request{SchemaVersion: protocol.Version, RequestID: "test", Operation: op, Class: cl, Arguments: json.RawMessage(args)})
	}
	if r := call("platform.status", protocol.Query, `{}`); !r.OK {
		t.Fatal(r)
	}
	if r := call("platform.status", protocol.Query, `{"root_override":true}`); r.OK {
		t.Fatal("platform status accepted spoof")
	}
	if r := call("namespace.apply", protocol.Run, `{"name":"Demo","proof":"forge","namespaces":["mnt:[1]"],"shell":"umount /"}`); r.OK {
		t.Fatal("arbitrary shell accepted")
	}
	if r := call("namespace.apply", protocol.Query, `{}`); r.OK {
		t.Fatal("incorrect operation class accepted")
	}
}
