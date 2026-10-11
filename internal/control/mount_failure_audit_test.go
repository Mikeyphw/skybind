package control

import (
	"context"
	"encoding/json"
	"errors"
	"skybind/internal/protocol"
	"strings"
	"testing"
)

func TestMountFailureTruthWithoutLeakingProviderText(t *testing.T) {
	e := New()
	var observed []string
	e.SetFailureAudit(func(operation, reason string) { observed = append(observed, operation+":"+reason) })
	e.Register("mount.start", protocol.Run, func(context.Context, json.RawMessage) (any, error) {
		return nil, errors.New("FUSE readiness/mount identity not observed (provider_permission_denied)")
	})
	response := e.Dispatch(context.Background(), protocol.Request{SchemaVersion: 1, RequestID: "q-test", Operation: "mount.start", Class: protocol.Run})
	if response.OK || response.Error == nil || response.Error.Code != "operation_failed" || response.Error.Message != "FUSE readiness/mount identity not observed (provider_permission_denied)" {
		t.Fatalf("unexpected response %+v", response)
	}
	if len(observed) != 1 || observed[0] != "mount.start:"+response.Error.Message {
		t.Fatal(observed)
	}
}

func TestMountFailureRejectsRawSecretAndUnknownCategories(t *testing.T) {
	for _, raw := range []string{
		"failed to connect --password=secret-token", "FUSE readiness/mount identity not observed (secret-to-leak)",
		"failed: https://remote.example/?token=secret", "",
	} {
		reason := safeOperationReason("mount.start", errors.New(raw))
		if strings.Contains(reason, "secret") || strings.Contains(reason, "https") || reason != "mount failed; internal cause unavailable (provider stderr not captured)" {
			t.Fatalf("untrusted reason exposed: %q", reason)
		}
	}
	if got := safeOperationReason("provider.config", errors.New("some-private-token")); got != "operation_failed" {
		t.Fatal(got)
	}
}
