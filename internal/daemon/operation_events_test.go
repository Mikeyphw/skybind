package daemon

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"skybind/internal/control"
	"skybind/internal/journal"
	"skybind/internal/opevents"
	"skybind/internal/protocol"
	"testing"
)

func TestPhaseAEventAPIAndControlLifecycle(t *testing.T) {
	root := t.TempDir()
	for _, dir := range []string{"events", "journal"} {
		if err := os.Mkdir(filepath.Join(root, dir), 0700); err != nil {
			t.Fatal(err)
		}
	}
	events, e := opevents.Open(filepath.Join(root, "events"))
	if e != nil {
		t.Fatal(e)
	}
	j, e := journal.Open(filepath.Join(root, "journal"))
	if e != nil {
		t.Fatal(e)
	}
	engine := control.New()
	engine.SetJournal(j)
	if e = engine.Register("mount.start", protocol.Run, func(context.Context, json.RawMessage) (any, error) { return map[string]string{"status": "test"}, nil }); e != nil {
		t.Fatal(e)
	}
	if e = RegisterOperationEvents(engine, nil, events); e != nil {
		t.Fatal(e)
	}
	r := engine.Dispatch(context.Background(), protocol.Request{SchemaVersion: 1, RequestID: "phase-a-test", Operation: "mount.start", Class: protocol.Run, Arguments: json.RawMessage(`{}`)})
	if !r.OK {
		t.Fatal(r)
	}
	q := func(raw string) protocol.Response {
		return engine.Dispatch(context.Background(), protocol.Request{SchemaVersion: 1, RequestID: "read-events", Operation: "operation.events", Class: protocol.Query, Arguments: json.RawMessage(raw)})
	}
	res := q(`{"cursor":0,"limit":64,"wait_ms":0}`)
	if !res.OK {
		t.Fatal(res)
	}
	b, _ := json.Marshal(res.Result)
	var page opevents.Page
	if e = json.Unmarshal(b, &page); e != nil {
		t.Fatal(e)
	}
	if len(page.Events) != 2 || page.Events[0].Type != "operation.started" || page.Events[1].Type != "operation.succeeded" {
		t.Fatalf("events %+v", page)
	}
	if page.Events[0].OperationID != page.Events[1].OperationID {
		t.Fatal("event identity drift")
	}
	id := page.Events[0].OperationID
	res = q(`{"cursor":0,"limit":3,"operation_id":"` + id + `"}`)
	if !res.OK {
		t.Fatal("filter failed", res)
	}
	if q(`{"cursor":0,"wait_ms":6000}`).OK || q(`{"limit":1000}`).OK || q(`{"extra":"secret"}`).OK {
		t.Fatal("unsafe event query accepted")
	}
	before, _ := os.ReadFile(filepath.Join(root, "events", "events-v1.json"))
	if string(before) == "" || string(before) == "secret" {
		t.Fatal("missing safe event spool")
	}
	resumed, e := opevents.Open(filepath.Join(root, "events"))
	if e != nil {
		t.Fatal(e)
	}
	replay, e := resumed.Poll(context.Background(), 0, 64, "", 0)
	if e != nil || len(replay.Events) != 2 {
		t.Fatal("replay failed", e)
	}
}
