package main

import (
	"bytes"
	"context"
	"errors"
	"skybind/internal/protocol"
	"strings"
	"testing"
)

func TestFeatureCLIOnlyRootAndNarrowOperations(t *testing.T) {
	calls := 0
	caller := func(_ context.Context, req protocol.Request) (protocol.Response, error) {
		calls++
		return protocol.Success(req.RequestID, map[string]any{"status": "ok"}), nil
	}
	for _, tc := range []struct {
		uid   int
		args  []string
		stdin string
	}{
		{10056, []string{"capabilities"}, ""},
		{10056, []string{"call", "mount.list", "--stdin"}, `{"api_version":1,"request_id":"x","arguments":{}}`},
		{0, []string{"call", "shell.exec", "--stdin"}, `{"api_version":1,"request_id":"x","arguments":{}}`},
		{0, []string{"call", "provider.crypt.password.set", "--stdin"}, `{"api_version":1,"request_id":"x","arguments":{}}`},
		{0, []string{"call", "mount.start", "--stdin"}, `{"api_version":2,"request_id":"x","arguments":{}}`},
		{0, []string{"call", "mount.start", "--stdin"}, `{"api_version":1,"request_id":"x","operation":"mount.stop","arguments":{}}`},
		{0, []string{"call", "mount.start", "--stdin", "--token"}, `{"api_version":1,"request_id":"x","arguments":{}}`},
	} {
		var out, errout bytes.Buffer
		if code := runFeature(tc.args, strings.NewReader(tc.stdin), &out, &errout, tc.uid, caller); code == 0 {
			t.Fatalf("bad request allowed %+v", tc)
		}
	}
	if calls != 0 {
		t.Fatalf("denied request reached backend %d times", calls)
	}
}
func TestFeatureCLIPropagatesRequestIdentityAndInnerDenial(t *testing.T) {
	body := `{"api_version":1,"request_id":"preserve_123","arguments":{"name":"demo","proof":"forged"}}`
	var out, errs bytes.Buffer
	caller := func(_ context.Context, req protocol.Request) (protocol.Response, error) {
		if req.Operation != "feature.execute" || req.Class != protocol.Query || req.RequestID != "preserve_123" || !bytes.Contains(req.Arguments, []byte(`"operation":"mount.start"`)) {
			t.Fatalf("unexpected backend request %+v", req)
		}
		return protocol.Success(req.RequestID, protocol.Fail(req.RequestID, "operation_failed", "operation", "execute", false)), nil
	}
	if c := runFeature([]string{"call", "mount.start", "--stdin"}, strings.NewReader(body), &out, &errs, 0, caller); c != 1 {
		t.Fatalf("backend denial lost: %d %s", c, out.String())
	}
	if !strings.Contains(out.String(), `"ok":false`) || strings.Contains(errs.String(), "forged") {
		t.Fatalf("response leak: %s %s", out.String(), errs.String())
	}
}
func TestFeatureCLIReadAndUnavailableTransport(t *testing.T) {
	var out, diag bytes.Buffer
	caller := func(_ context.Context, req protocol.Request) (protocol.Response, error) {
		if req.Operation == "feature.capabilities" {
			return protocol.Success(req.RequestID, map[string]int{"api_version": 1}), nil
		}
		return protocol.Success(req.RequestID, protocol.Success(req.RequestID, map[string]string{"status": "STOPPED"})), nil
	}
	if c := runFeature([]string{"capabilities"}, strings.NewReader(""), &out, &diag, 0, caller); c != 0 || !strings.Contains(out.String(), "api_version") {
		t.Fatalf("caps %d %s", c, out.String())
	}
	out.Reset()
	if c := runFeature([]string{"call", "mount.status", "--stdin"}, strings.NewReader(`{"api_version":1,"request_id":"look","arguments":{"name":"Demo"}}`), &out, &diag, 0, caller); c != 0 || !strings.Contains(out.String(), "STOPPED") {
		t.Fatalf("read %d %s", c, out.String())
	}
	if c := runFeature([]string{"capabilities"}, strings.NewReader(""), &out, &diag, 0, func(context.Context, protocol.Request) (protocol.Response, error) {
		return protocol.Response{}, errors.New("private_path_canary")
	}); c != 1 || strings.Contains(diag.String(), "private_path_canary") {
		t.Fatal("transport detail leaked")
	}
}
