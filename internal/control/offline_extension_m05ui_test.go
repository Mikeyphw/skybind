package control

import (
	"context"
	"encoding/json"
	"skybind/internal/protocol"
	"testing"
)

func TestM05UIOptionalOperationsExplicitWithoutFrozenCatalogDrift(t *testing.T) {
	e := New()
	for name, class := range offlineExtension {
		item, ok := Lookup(name)
		if !ok || item.OperationClass != class {
			t.Fatalf("missing typed extension %s", name)
		}
		if err := e.Register(name, class, func(context.Context, json.RawMessage) (any, error) { return "ok", nil }); err != nil {
			t.Fatal(err)
		}
		wrong := protocol.Query
		if class == protocol.Query {
			wrong = protocol.Run
		}
		res := e.Dispatch(context.Background(), protocol.Request{SchemaVersion: 1, RequestID: "m05", Operation: name, Class: wrong, Arguments: json.RawMessage(`{}`)})
		if res.OK || res.Error.Code != "class_mismatch" {
			t.Fatalf("wrong class allowed %s: %+v", name, res)
		}
	}
	if err := e.Register("offline.shell", protocol.Run, func(context.Context, json.RawMessage) (any, error) { return nil, nil }); err == nil {
		t.Fatal("unexpected root shell operation allowed")
	}
	c, err := e.Catalog()
	if err != nil || c.Total != 59 || len(c.Operations) != 59 {
		t.Fatalf("CFS1 catalog drift: %+v %v", c, err)
	}
	for _, item := range c.Operations {
		if _, ok := offlineExtension[item.Name]; ok {
			t.Fatal("optional offline extension silently entered frozen catalog")
		}
	}
}
