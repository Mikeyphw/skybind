package daemon

import (
	"context"
	"encoding/json"
	"path/filepath"
	"testing"

	"skybind/internal/control"
	"skybind/internal/offline"
	"skybind/internal/protocol"
)

func TestM06BTypedReconnectReviewAuthAndNoImplicitUpload(t *testing.T) {
	store := offline.New(filepath.Join(t.TempDir(), "offline"), nil, nil)
	engine := control.New()
	tasks := offline.NewTaskManager(store)
	if err := RegisterOffline(engine, tasks, store); err != nil {
		t.Fatal(err)
	}
	dispatch := func(op string, class protocol.Class, args string) protocol.Response {
		return engine.Dispatch(context.Background(), protocol.Request{SchemaVersion: 1, RequestID: "m06b", Operation: op, Class: class, Arguments: json.RawMessage(args)})
	}
	if !dispatch("offline.write.review", protocol.Query, `{}`).OK {
		t.Fatal("cannot inspect review settings")
	}
	for _, tc := range []struct {
		op    string
		class protocol.Class
		body  string
	}{
		{"offline.write.review", protocol.Query, `{"shell":"sh"}`},
		{"offline.write.review", protocol.Run, `{}`},
		{"offline.write.reconcile", protocol.Run, `{"mount":"../unsafe"}`},
		{"offline.write.reconcile", protocol.Run, `{"mount":""}`},
		{"offline.write.reconcile", protocol.Run, `{"mount":"drive","exec":"id"}`},
		{"offline.write.auto-review", protocol.Run, `{"enabled":"yes"}`},
		{"offline.write.auto-review", protocol.Run, `{}`},
		{"offline.write.auto-review", protocol.Query, `{"enabled":true}`},
		{"offline.write.auto-review", protocol.Run, `{"enabled":true,"remote":"../../foo"}`},
		{"offline.write.reconcile-upload", protocol.Run, `{"acknowledge":true}`},
		{"offline.write.overwrite", protocol.Run, `{}`},
	} {
		if dispatch(tc.op, tc.class, tc.body).OK {
			t.Fatalf("unsafe operation permitted %+v", tc)
		}
	}
	if !dispatch("offline.write.auto-review", protocol.Run, `{"enabled":true}`).OK {
		t.Fatal("cannot opt in")
	}
	st, err := store.ReviewSettings()
	if err != nil || !st.AutoOnReconnect {
		t.Fatal("opt-in not persisted")
	}
	if !dispatch("offline.write.auto-review", protocol.Run, `{"enabled":false}`).OK {
		t.Fatal("cannot opt out")
	}
}
