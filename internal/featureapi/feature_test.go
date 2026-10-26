package featureapi

import (
	"skybind/internal/control"
	"skybind/internal/protocol"
	"strings"
	"testing"
)

func TestDiscoverReportsOnlyFiniteFeaturesAndActualHandlers(t *testing.T) {
	got := Discover([]control.Descriptor{
		{Operation: "mount.start", Class: protocol.Run, Implemented: true},
		{Operation: "mount.stop", Class: protocol.Query, Implemented: true},
		{Operation: "operation.events", Class: protocol.Query, Implemented: true},
		{Operation: "provider.crypt.password.set", Class: protocol.Run, Implemented: true},
	})
	if got.APIVersion != 1 || got.ProtocolVersion != 1 || got.Authorization != "root_only" {
		t.Fatalf("contract drift: %+v", got)
	}
	seen := map[string]Capability{}
	previous := ""
	for _, c := range got.Operations {
		if c.Operation <= previous {
			t.Fatal("capabilities not sorted or duplicated")
		}
		previous = c.Operation
		seen[c.Operation] = c
		if _, ok := ClassFor(c.Operation); !ok {
			t.Fatalf("unexpected public op: %s", c.Operation)
		}
	}
	if len(seen) != 16 || !seen["mount.start"].Implemented || !seen["mount.start"].PreviewRequired || seen["mount.stop"].Implemented || !seen["operation.events"].Implemented {
		t.Fatalf("wrong capability truth: %+v", seen)
	}
	if _, ok := seen["provider.crypt.password.set"]; ok {
		t.Fatal("credential API exposed")
	}
	for _, n := range []string{"rclone.copy", "shell.exec", "provider.crypt.password.set", "config.apply", "feature.execute", "remote.transfer.start"} {
		if _, ok := ClassFor(n); ok {
			t.Fatalf("dangerous internal operation exposed: %s", n)
		}
	}
}
func TestDecodeCallStrictEnvelopes(t *testing.T) {
	accepted := []string{
		`{"api_version":1,"request_id":"op_123","arguments":{}}`,
		`{"request_id":"retry_A","arguments":{"name":"Demo","proof":"p"},"api_version":1}`,
		`{"api_version":1,"request_id":"op_123","operation":"mount.start","arguments":{"name":"M"}}`,
	}
	for _, data := range accepted {
		if _, err := DecodeCall(strings.NewReader(data)); err != nil {
			t.Fatalf("rejected %s: %v", data, err)
		}
	}
	invalid := []string{
		`{}`, `{"api_version":2,"request_id":"req","arguments":{}}`,
		`{"api_version":1,"request_id":"a/b","arguments":{}}`,
		`{"api_version":1,"request_id":"req","arguments":[]}`,
		`{"api_version":1,"request_id":"req","arguments":null}`,
		`{"api_version":1,"request_id":"req","arguments":{ },"shell":"id"}`,
		`{"api_version":1,"request_id":"first","request_id":"second","arguments":{}}`,
		`{"api_version":1,"request_id":"req","arguments":{}} {}`,
		`{"api_version":1,"request_id":"req","operation":"shell.exec","arguments":{}}`,
		`{"api_version":1,"request_id":"req"}`,
		`{"api_version":1,"request_id":"req","arguments":false}`,
		`{"api_version":1,"request_id":"req","arguments":{"name":"Demo","name":"Evil"}}`,
		`{"api_version":1,"request_id":"req","arguments":{"nested":{"proof":"a","proof":"b"}}}`,
		strings.Repeat("a", MaxCallBytes+1),
	}
	for _, data := range invalid {
		if _, err := DecodeCall(strings.NewReader(data)); err == nil {
			t.Fatalf("accepted invalid envelope: %.100s", data)
		}
	}
}
