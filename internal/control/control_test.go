package control

import (
	"context"
	"encoding/json"
	"skybind/internal/protocol"
	"testing"
)

func TestAllowlist(t *testing.T) {
	e := New()
	if err := e.Register("runtime.status", protocol.Query, func(context.Context, json.RawMessage) (any, error) { return 1, nil }); err != nil {
		t.Fatal(err)
	}
	for _, x := range []struct {
		name string
		cls  protocol.Class
	}{{"shell.exec", protocol.Run}, {"runtime.status", protocol.Run}} {
		r := e.Dispatch(context.Background(), protocol.Request{SchemaVersion: 1, RequestID: "a", Operation: x.name, Class: x.cls})
		if r.OK {
			t.Fatal("forbidden operation allowed")
		}
	}
}
