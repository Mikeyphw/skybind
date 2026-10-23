package control

import (
	"context"
	"encoding/json"
	"skybind/internal/mounts/config"
	"skybind/internal/protocol"
	"strings"
	"testing"
)

func TestConfigFieldFailureContainsOnlyBoundedMetadata(t *testing.T) {
	e := New()
	e.Register("config.validate", protocol.Query, func(_ context.Context, _ json.RawMessage) (any, error) {
		return nil, &config.FieldValidationError{Issue: config.FieldViolation{Index: 2, Field: "mountpoint", Code: "OVERLAPPING_DESTINATION"}}
	})
	res := e.Dispatch(context.Background(), protocol.Request{SchemaVersion: 1, RequestID: "test", Operation: "config.validate", Class: protocol.Query, Arguments: json.RawMessage(`{}`)})
	if res.OK || res.Error == nil || len(res.Error.FieldErrors) != 1 {
		t.Fatalf("missing typed failed result: %+v", res)
	}
	issue := res.Error.FieldErrors[0]
	if issue.Index != 2 || issue.Field != "mountpoint" || issue.Code != "OVERLAPPING_DESTINATION" || res.Error.Message != "operation_failed" {
		t.Fatalf("untrusted raw error or misattributed field: %+v", res.Error)
	}
	b, _ := json.Marshal(res)
	if strings.Contains(string(b), "/mnt/private") {
		t.Fatal("leaked input values")
	}
}
func TestOtherOperationsNeverGetConfigFieldDetails(t *testing.T) {
	e := New()
	e.Register("config.apply", protocol.Run, func(_ context.Context, _ json.RawMessage) (any, error) {
		return nil, &config.FieldValidationError{Issue: config.FieldViolation{Index: 0, Field: "remote", Code: "INVALID_REMOTE"}}
	})
	res := e.Dispatch(context.Background(), protocol.Request{SchemaVersion: 1, RequestID: "test", Operation: "config.apply", Class: protocol.Run, Arguments: json.RawMessage(`{}`)})
	if res.Error == nil || len(res.Error.FieldErrors) != 0 {
		t.Fatalf("cross-class validation leak %+v", res)
	}
}
