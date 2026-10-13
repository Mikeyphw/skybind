package daemon

import (
	"context"
	"encoding/json"
	"path/filepath"
	"skybind/internal/control"
	"skybind/internal/offline"
	"skybind/internal/protocol"
	"testing"
)

func TestM06AuthenticatedExtensionRequiresTypedArgsAndExplicitAck(t *testing.T) {
	store := offline.New(filepath.Join(t.TempDir(), "offline"), nil, nil)
	tasks := offline.NewTaskManager(store)
	engine := control.New()
	if err := RegisterOffline(engine, tasks, store); err != nil {
		t.Fatal(err)
	}
	dispatch := func(name string, class protocol.Class, args string) protocol.Response {
		return engine.Dispatch(context.Background(), protocol.Request{SchemaVersion: 1, RequestID: "m06", Operation: name, Class: class, Arguments: json.RawMessage(args)})
	}
	if !dispatch("offline.write.list", protocol.Query, `{}`).OK {
		t.Fatal("write list unavailable")
	}
	for _, tc := range []struct {
		name  string
		class protocol.Class
		body  string
	}{
		{"offline.write.list", protocol.Query, `{"shell":"id"}`},
		{"offline.write.list", protocol.Run, `{}`},
		{"offline.write.draft", protocol.Run, `{"mount":"drive","path":"../evil"}`},
		{"offline.write.stage", protocol.Run, `{"mount":"drive","path":"/etc/passwd"}`},
		{"offline.write.draft", protocol.Run, `{"mount":"drive","path":"a","shell":"sh"}`},
		{"offline.write.check", protocol.Query, `{"id":"bad","extra":true}`},
		{"offline.write.upload-copy", protocol.Run, `{"id":"00000000000000000000000000000000","acknowledge":false}`},
		{"offline.write.upload-copy", protocol.Run, `{"id":"00000000000000000000000000000000","acknowledge":true,"dest":"drive:original"}`},
		{"offline.write.upload-copy", protocol.Run, `{"id":"00000000000000000000000000000000","acknowledge":true}`},
		{"offline.write.overwrite", protocol.Run, `{}`},
	} {
		if dispatch(tc.name, tc.class, tc.body).OK {
			t.Fatalf("unsafe action accepted: %+v", tc)
		}
	}
}
