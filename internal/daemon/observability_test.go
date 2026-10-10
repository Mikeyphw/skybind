package daemon

import (
	"context"
	"os"
	"path/filepath"
	"skybind/internal/diagnostics"
	"skybind/internal/doctor"
	"skybind/internal/protocol"
	"strings"
	"testing"
)

func TestDoctorAndSanitizedAudit(t *testing.T) {
	root := filepath.Join(t.TempDir(), "logs")
	if e := os.Mkdir(root, 0700); e != nil {
		t.Fatal(e)
	}
	logs, e := diagnostics.Open(root)
	if e != nil {
		t.Fatal(e)
	}
	engine := EngineWithObservability(nil, nil, nil, nil, nil, nil, nil, nil, nil, nil, nil, logs, nil, doctor.Reporter{})
	r := engine.Dispatch(context.Background(), protocol.Request{SchemaVersion: 1, RequestID: "req_abc", Operation: "doctor.report", Class: protocol.Query, Arguments: []byte(`{}`)})
	if !r.OK {
		t.Fatal(r)
	}
	bad := engine.Dispatch(context.Background(), protocol.Request{SchemaVersion: 1, RequestID: "req_def", Operation: "unknown.password=private-canary", Class: protocol.Query, Arguments: []byte(`{"password":"hunter2"}`)})
	if bad.OK {
		t.Fatal("unknown operation success")
	}
	out, e := logs.Query(diagnostics.Filter{Limit: 20})
	if e != nil || len(out) != 2 {
		t.Fatal(e, out)
	}
	b, e := os.ReadFile(filepath.Join(root, "skybind.jsonl"))
	if e != nil {
		t.Fatal(e)
	}
	if strings.Contains(string(b), "hunter2") || strings.Contains(string(b), "private-canary") {
		t.Fatal("audit leaked request secrets")
	}
}
