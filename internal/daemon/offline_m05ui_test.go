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

func TestM05UITypedValidationAndNoShell(t *testing.T) {
	store := offline.New(filepath.Join(t.TempDir(), "offline"), nil, nil)
	tasks := offline.NewTaskManager(store)
	e := control.New()
	if err := RegisterOffline(e, tasks, store); err != nil {
		t.Fatal(err)
	}
	dispatch := func(name string, class protocol.Class, args string) protocol.Response {
		return e.Dispatch(context.Background(), protocol.Request{SchemaVersion: 1, RequestID: "m05ui", Operation: name, Class: class, Arguments: json.RawMessage(args)})
	}
	if !dispatch("offline.list", protocol.Query, `{}`).OK {
		t.Fatal("cannot query empty offline store")
	}
	if !dispatch("offline.tasks", protocol.Query, `{}`).OK {
		t.Fatal("cannot query offline task list")
	}
	for _, c := range []struct {
		name  string
		class protocol.Class
		args  string
	}{
		{"offline.list", protocol.Query, `{"x":1}`},
		{"offline.pin", protocol.Run, `{"mount":"drive","path":"a","shell":"rm"}`},
		{"offline.pin", protocol.Run, `{"mount":"drive","path":"../private"}`},
		{"offline.export", protocol.Run, `{"mount":"drive","path":"/etc/passwd"}`},
		{"offline.quota", protocol.Run, `{"gib":65}`},
		{"offline.cancel", protocol.Cancel, `{"id":"missing"}`},
		{"offline.pin", protocol.Query, `{}`},
		{"offline.shell", protocol.Run, `{}`},
	} {
		if dispatch(c.name, c.class, c.args).OK {
			t.Fatalf("allowed unsafe operation %s", c.name)
		}
	}
}
