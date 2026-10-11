package daemon

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"skybind/internal/mounts/config"
	"skybind/internal/protocol"
	"testing"
)

func TestConfigurationRPCPreviewApplyAndCapabilities(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "private")
	if err := os.Mkdir(dir, 0700); err != nil {
		t.Fatal(err)
	}
	store, err := config.Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	eng := EngineWithConfig(nil, store)
	call := func(name string, cl protocol.Class, args string) protocol.Response {
		return eng.Dispatch(context.Background(), protocol.Request{SchemaVersion: 1, RequestID: "demo", Operation: name, Class: cl, Arguments: json.RawMessage(args)})
	}
	caps := call("system.capabilities", protocol.Query, "{}")
	if !caps.OK {
		t.Fatal(caps)
	}
	b, _ := json.Marshal(caps.Result)
	var catalog struct {
		Total      int `json:"total"`
		Operations []struct {
			Name        string `json:"name"`
			Implemented bool   `json:"implemented"`
		} `json:"operations"`
	}
	if err := json.Unmarshal(b, &catalog); err != nil {
		t.Fatal(err)
	}
	if catalog.Total != 57 || len(catalog.Operations) != 57 {
		t.Fatalf("invalid capability catalog: %+v", catalog)
	}
	for _, v := range catalog.Operations {
		if v.Name == "mount.start" && v.Implemented {
			t.Fatal("future mount start advertised")
		}
	}
	if bad := call("config.snapshot", protocol.Query, `{"unexpected":true}`); bad.OK {
		t.Fatal("unexpected extra field accepted")
	}
	current := call("config.snapshot", protocol.Query, "{}")
	if !current.OK {
		t.Fatal(current)
	}
	candidate := `{"schema_version":2,"revision":0,"mounts":[]}`
	envelope := `{"candidate":` + candidate + `}`
	prev := call("config.preview", protocol.Preview, envelope)
	if !prev.OK {
		t.Fatalf("config.preview %+v", prev)
	}
	planBytes, _ := json.Marshal(prev.Result)
	var plan struct {
		Token string `json:"proof"`
	}
	_ = json.Unmarshal(planBytes, &plan)
	if plan.Token == "" {
		t.Fatal("missing proof")
	}
	apply := call("config.apply", protocol.Run, `{"candidate":`+candidate+`,"proof":"`+plan.Token+`"}`)
	if !apply.OK {
		t.Fatalf("config apply: %+v", apply)
	}
	if again := call("config.apply", protocol.Run, `{"candidate":`+candidate+`,"proof":"`+plan.Token+`"}`); again.OK {
		t.Fatal("replayed proof accepted")
	}
	if unknown := call("mount.start", protocol.Run, "{}"); unknown.OK || unknown.Error.Code != "not_implemented" {
		t.Fatalf("future run incorrectly advertised: %+v", unknown)
	}
}
