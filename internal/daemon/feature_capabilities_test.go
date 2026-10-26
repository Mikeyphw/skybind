package daemon

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"skybind/internal/control"
	"skybind/internal/featureapi"
	"skybind/internal/journal"
	"skybind/internal/protocol"
	"sync"
	"testing"
)

func TestFeatureAPITruthfulCapabilitiesAndFailClosedReplay(t *testing.T) {
	dir := t.TempDir()
	jdir := filepath.Join(dir, "journal")
	if err := os.Mkdir(jdir, 0700); err != nil {
		t.Fatal(err)
	}
	journalStore, err := journal.Open(jdir)
	if err != nil {
		t.Fatal(err)
	}
	engine := control.New()
	engine.SetJournal(journalStore)
	mutations := 0
	err = engine.Register("mount.start", protocol.Run, func(_ context.Context, raw json.RawMessage) (any, error) {
		var input struct {
			Name  string `json:"name"`
			Proof string `json:"proof"`
		}
		if err := protocol.StrictBytes(raw, &input); err != nil || input.Proof != "verified" {
			return nil, os.ErrPermission
		}
		mutations++
		return map[string]string{"state": "STARTED"}, nil
	})
	if err != nil {
		t.Fatal(err)
	}
	if err = RegisterFeatureCapabilities(engine, journalStore); err != nil {
		t.Fatal(err)
	}
	ask := func(id, op string, args string) protocol.Response {
		raw, _ := json.Marshal(featureapi.Call{APIVersion: 1, RequestID: id, Operation: op, Arguments: json.RawMessage(args)})
		response := engine.Dispatch(context.Background(), protocol.Request{SchemaVersion: 1, RequestID: id, Operation: "feature.execute", Class: protocol.Query, Arguments: raw})
		if !response.OK {
			t.Fatalf("outer rejected: %+v", response)
		}
		data, _ := json.Marshal(response.Result)
		var inner protocol.Response
		if err := json.Unmarshal(data, &inner); err != nil {
			t.Fatal(err)
		}
		return inner
	}
	caps := engine.Dispatch(context.Background(), protocol.Request{SchemaVersion: 1, RequestID: "caps", Operation: "feature.capabilities", Class: protocol.Query, Arguments: []byte(`{}`)})
	if !caps.OK {
		t.Fatal(caps)
	}
	b, _ := json.Marshal(caps.Result)
	var discovered featureapi.Capabilities
	if err = json.Unmarshal(b, &discovered); err != nil {
		t.Fatal(err)
	}
	var enabled int
	for _, v := range discovered.Operations {
		if v.Implemented {
			enabled++
			if v.Operation != "mount.start" {
				t.Fatalf("claimed unregistered feature %+v", v)
			}
		}
	}
	if enabled != 1 {
		t.Fatal("expected one real feature")
	}
	if got := ask("denied", "mount.start", `{"name":"demo","proof":"forged"}`); got.OK || mutations != 0 {
		t.Fatalf("forged proof executed %+v", got)
	}
	if got := ask("accept", "mount.start", `{"name":"demo","proof":"verified"}`); !got.OK || mutations != 1 {
		t.Fatalf("first mutation denied %+v", got)
	}
	if got := ask("accept", "mount.start", `{"name":"demo","proof":"verified"}`); got.OK || got.Error.Code != "duplicate_request_use_operation_status" || mutations != 1 {
		t.Fatalf("replay executed %+v", got)
	}
	// Mutation identity is replay-blocked even when reused with another operation.
	if got := ask("denied", "mount.start", `{"name":"demo","proof":"verified"}`); got.OK || mutations != 1 {
		t.Fatal("failed request ID replay allowed")
	}
	if r := engine.Dispatch(context.Background(), protocol.Request{SchemaVersion: 1, RequestID: "q", Operation: "feature.capabilities", Class: protocol.Query, Arguments: []byte(`{"spoof":true}`)}); r.OK {
		t.Fatal("fake feature capabilities accepted")
	}
}
func TestFeatureMutationDuplicateConcurrentRequests(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "journal")
	if err := os.Mkdir(dir, 0700); err != nil {
		t.Fatal(err)
	}
	j, err := journal.Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	engine := control.New()
	engine.SetJournal(j)
	var mu sync.Mutex
	count := 0
	if err = engine.Register("mount.stop", protocol.Run, func(context.Context, json.RawMessage) (any, error) { mu.Lock(); count++; mu.Unlock(); return true, nil }); err != nil {
		t.Fatal(err)
	}
	if err = RegisterFeatureCapabilities(engine, j); err != nil {
		t.Fatal(err)
	}
	payload := json.RawMessage(`{"api_version":1,"operation":"mount.stop","request_id":"same_id","arguments":{"name":"Demo"}}`)
	var wg sync.WaitGroup
	for i := 0; i < 12; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			engine.Dispatch(context.Background(), protocol.Request{SchemaVersion: 1, RequestID: "same_id", Operation: "feature.execute", Class: protocol.Query, Arguments: payload})
		}()
	}
	wg.Wait()
	if count != 1 {
		t.Fatalf("duplicate request caused %d side effects", count)
	}
}
