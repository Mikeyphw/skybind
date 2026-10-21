package brokeripc

// RequestOnce is a minimal Go consumer transport that keeps the caller's
// credentials entirely in memory. It does not issue grants, fall back to
// native rclone, read a config file or select an arbitrary socket endpoint.
// A producer may adopt this wire contract independently of Skybind versions.
import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net"
	"time"
)

func RequestOnce(ctx context.Context, request Request) (Response, error) {
	return requestAt(ctx, ConsumerAbstractEndpoint, request)
}

func requestAt(ctx context.Context, endpoint string, request Request) (Response, error) {
	var result Response
	if ctx == nil || request.Version != ProtocolVersion ||
		len(request.Token) != 64 || len(request.Operation) == 0 ||
		len(request.Remote) == 0 || len(request.Path) > 4096 {
		return result, errors.New("r1_invalid_consumer_request")
	}
	d := net.Dialer{Timeout: 3 * time.Second}
	conn, err := d.DialContext(ctx, "unix", endpoint)
	if err != nil {
		return result, err
	}
	defer conn.Close()
	unix, ok := conn.(*net.UnixConn)
	if !ok {
		return result, errors.New("r1_consumer_unix_required")
	}
	deadline := time.Now().Add(5 * time.Second)
	if d, ok := ctx.Deadline(); ok && d.Before(deadline) {
		deadline = d
	}
	if err = unix.SetDeadline(deadline); err != nil {
		return result, err
	}
	encoded, err := json.Marshal(request)
	if err != nil || len(encoded) > MaxRequestBytes {
		return result, errors.New("r1_request_too_large")
	}
	if _, err = unix.Write(encoded); err != nil {
		return result, err
	}
	// The R1 server reads exactly one bounded request until EOF; CloseWrite
	// signals the end without closing the reply-reading half of this socket.
	if err = unix.CloseWrite(); err != nil {
		return result, err
	}
	body, err := io.ReadAll(io.LimitReader(unix, MaxResponseBytes+1))
	if err != nil || len(body) == 0 || len(body) > MaxResponseBytes {
		return result, errors.New("r1_invalid_broker_response")
	}
	decoder := json.NewDecoder(bytes.NewReader(body))
	decoder.DisallowUnknownFields()
	if err = decoder.Decode(&result); err != nil {
		return Response{}, errors.New("r1_invalid_broker_response")
	}
	if err = decoder.Decode(new(any)); err != io.EOF || result.Version != ProtocolVersion || (result.OK && (!json.Valid(result.Result) || result.Error != "")) || (!result.OK && len(result.Result) != 0 && string(result.Result) != "null") {
		return Response{}, errors.New("r1_invalid_broker_response")
	}
	return result, nil
}
