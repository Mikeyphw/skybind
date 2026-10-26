package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"skybind/internal/daemon"
	"skybind/internal/featureapi"
	"skybind/internal/paths"
	"skybind/internal/protocol"
)

type featureCaller func(context.Context, protocol.Request) (protocol.Response, error)

func featureCommand(args []string) int {
	return runFeature(args, os.Stdin, os.Stdout, os.Stderr, os.Geteuid(),
		func(ctx context.Context, req protocol.Request) (protocol.Response, error) {
			return daemon.Call(ctx, paths.DaemonSocket, req)
		})
}

// The injected transport/UID make authorization and request handling
// independently testable without starting a privileged process.
func runFeature(args []string, input io.Reader, output, diagnostics io.Writer, uid int, call featureCaller) int {
	if uid != 0 {
		fmt.Fprintln(diagnostics, "feature API requires root")
		return 1
	}
	if len(args) == 1 && args[0] == "capabilities" {
		res, err := call(context.Background(), protocol.Request{SchemaVersion: protocol.Version,
			RequestID: "feature-capabilities-v1", Operation: "feature.capabilities", Class: protocol.Query, Arguments: json.RawMessage(`{}`)})
		if err != nil {
			fmt.Fprintln(diagnostics, "feature transport unavailable")
			return 1
		}
		if json.NewEncoder(output).Encode(res) != nil || !res.OK {
			return 1
		}
		return 0
	}
	if len(args) != 3 || args[0] != "call" || args[2] != "--stdin" {
		fmt.Fprintln(diagnostics, "usage: skybind feature capabilities | call <operation> --stdin (root only)")
		return 2
	}
	_, ok := featureapi.ClassFor(args[1])
	if !ok {
		fmt.Fprintln(diagnostics, "feature not allowed")
		return 2
	}
	envelope, err := featureapi.DecodeCall(input)
	if err != nil {
		fmt.Fprintln(diagnostics, "invalid feature request")
		return 2
	}
	if envelope.Operation != "" {
		fmt.Fprintln(diagnostics, "feature operation must come from CLI")
		return 2
	}
	envelope.Operation = args[1]
	wrapped, err := json.Marshal(envelope)
	if err != nil {
		return 2
	}
	req := protocol.Request{SchemaVersion: protocol.Version, RequestID: envelope.RequestID,
		Operation: "feature.execute", Class: protocol.Query, Arguments: wrapped}
	res, err := call(context.Background(), req)
	if err != nil {
		fmt.Fprintln(diagnostics, "feature transport unavailable")
		return 1
	}
	if !res.OK {
		fmt.Fprintln(diagnostics, "feature service unavailable")
		return 1
	}
	b, err := json.Marshal(res.Result)
	if err != nil {
		return 1
	}
	var inner protocol.Response
	if err = protocol.StrictBytes(b, &inner); err != nil || inner.SchemaVersion != protocol.Version || inner.RequestID != envelope.RequestID {
		fmt.Fprintln(diagnostics, "invalid feature response")
		return 1
	}
	if json.NewEncoder(output).Encode(inner) != nil || !inner.OK {
		return 1
	}
	return 0
}
