package writeback

import (
	"encoding/json"
	"strings"
	"testing"
)

func raw(q, a, e, use any) []byte {
	b, _ := json.Marshal(map[string]any{"diskCache": map[string]any{"uploadsQueued": q, "uploadsInProgress": a, "erroredFiles": e, "path": "/private/secret"}, "inUse": use, "remote": "secret"})
	return b
}
func TestVFSStateClassification(t *testing.T) {
	for _, tc := range []struct {
		name    string
		payload []byte
		want    string
		safe    bool
	}{
		{"idle", raw(0, 0, 0, 0), "idle", true},
		{"queued", raw(1, 0, 0, 0), "busy", false},
		{"uploading", raw(0, 2, 0, 0), "busy", false},
		{"reference_only", raw(0, 0, 0, 1), "idle", true},
		{"failed", raw(0, 0, 1, 0), "errored", false},
		{"missing", []byte(`{"diskCache":{},"inUse":0}`), "unknown", false},
		{"no_in_use", []byte(`{"diskCache":{"uploadsQueued":0,"uploadsInProgress":0,"erroredFiles":0}}`), "unknown", false},
		{"fraction", raw(1.5, 0, 0, 0), "unknown", false},
		{"negative", raw(-1, 0, 0, 0), "unknown", false},
		{"string", raw("0", 0, 0, 0), "unknown", false},
		{"overflow", raw(1e15, 0, 0, 0), "unknown", false},
		{"invalid", []byte(`oops`), "unknown", false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			v, _ := ParseVFS("safe", tc.payload)
			if v.State != tc.want || v.Safe() != tc.safe {
				t.Fatalf("got %+v", v)
			}
			jsonBytes, _ := json.Marshal(v)
			if strings.Contains(string(jsonBytes), "secret") || strings.Contains(string(jsonBytes), "/private/") {
				t.Fatal("leaked path")
			}
		})
	}
}
