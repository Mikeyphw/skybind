package control

import (
	"context"
	"encoding/json"
	"skybind/internal/protocol"
	"testing"
)

func TestCatalogTruthAndDeterminism(t *testing.T) {
	e := New()
	_ = e.Register("runtime.status", protocol.Query, func(context.Context, json.RawMessage) (any, error) { return map[string]bool{"ready": false}, nil })
	c, err := e.Catalog()
	if err != nil {
		t.Fatal(err)
	}
	if c.Total != 59 || len(c.Operations) != 59 || c.ProtocolVersion != protocol.Version {
		t.Fatalf("wrong catalog %+v", c)
	}
	implemented := 0
	for i, item := range c.Operations {
		if i > 0 && c.Operations[i-1].Name >= item.Name {
			t.Fatalf("unordered catalog")
		}
		if item.ArgumentsSchema == "" || item.Cancellation == "" {
			t.Fatalf("missing schema/cancellation %s", item.Name)
		}
		if item.Implemented {
			implemented++
			if item.Name != "runtime.status" {
				t.Fatalf("fabricated implementation %s", item.Name)
			}
		}
	}
	if implemented != 1 {
		t.Fatalf("implemented=%d", implemented)
	}
	for _, v := range []string{"mount.start", "namespace.apply", "provider.crypt.create"} {
		item, ok := Lookup(v)
		if !ok || item.Implemented {
			t.Fatalf("future op must not claim implemented: %s", v)
		}
		res := e.Dispatch(context.Background(), protocol.Request{SchemaVersion: protocol.Version, RequestID: "a", Operation: v, Class: item.OperationClass})
		if res.OK || res.Error == nil || res.Error.Code != "not_implemented" {
			t.Fatalf("unsupported op must fail clearly: %+v", res)
		}
	}
}
func TestClassDriftAndArbitraryRegistrationRejected(t *testing.T) {
	e := New()
	f := func(context.Context, json.RawMessage) (any, error) { return nil, nil }
	if e.Register("mount.start", protocol.Query, f) == nil {
		t.Fatal("catalog class drift registered")
	}
	if e.Register("shell.exec", protocol.Run, f) == nil {
		t.Fatal("arbitrary handler registered")
	}
	if e.Register("mount.start", protocol.Run, f) != nil {
		t.Fatal("registered known class")
	}
	c, _ := e.Catalog()
	for _, a := range c.Operations {
		if a.Name == "mount.start" && !a.Implemented {
			t.Fatal("registration not reflected")
		}
	}
}
