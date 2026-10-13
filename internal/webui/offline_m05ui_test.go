package webui

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"skybind/internal/protocol"
	"testing"
)

func TestM05UIEmbeddedAllowsOnlyExplicitTypedOfflineOperations(t *testing.T) {
	mk := func(name string, class string) string {
		b, _ := json.Marshal(map[string]any{"schema_version": 1, "request_id": "m05ui", "client": map[string]any{"name": "skybind-webui", "version": "0.1.0", "protocol": map[string]int{"min": 1, "max": 1}}, "operation": map[string]any{"name": name, "class": class, "args": map[string]any{}}})
		return base64.RawURLEncoding.EncodeToString(b)
	}
	called := 0
	call := func(_ context.Context, r protocol.Request) (protocol.Response, error) {
		called++
		return protocol.Success(r.RequestID, map[string]bool{"ok": true}), nil
	}
	for _, tc := range []struct{ name, class string }{{"offline.list", "query"}, {"offline.tasks", "query"}, {"offline.pin", "run"}, {"offline.cancel", "cancel"}} {
		if _, err := Embedded(context.Background(), mk(tc.name, tc.class), call); err != nil {
			t.Fatalf("reject registered extension %s: %v", tc.name, err)
		}
	}
	if called != 4 {
		t.Fatalf("expected 4 called got %d", called)
	}
	if _, err := Embedded(context.Background(), mk("offline.shell", "run"), call); err == nil {
		t.Fatal("arbitrary exec bridge accepted")
	}
}
