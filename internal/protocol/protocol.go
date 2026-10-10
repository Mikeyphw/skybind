// Package protocol is Skybind's bounded, strictly typed local RPC wire contract.
package protocol

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"strings"
)

const Version = 1
const MaxEnvelope = 65536
const MaxResponse = 262144

type Class string

const (
	Query     Class = "query"
	Preview   Class = "preview"
	Run       Class = "run"
	Cancel    Class = "cancel"
	Reconcile Class = "reconcile"
)

func (c Class) Valid() bool {
	return c == Query || c == Preview || c == Run || c == Cancel || c == Reconcile
}

type Request struct {
	SchemaVersion int             `json:"schema_version"`
	RequestID     string          `json:"request_id"`
	Operation     string          `json:"operation"`
	Class         Class           `json:"class"`
	Arguments     json.RawMessage `json:"arguments,omitempty"`
}
type Fault struct {
	Code      string `json:"code"`
	Category  string `json:"category"`
	Stage     string `json:"stage"`
	Message   string `json:"message"`
	Retryable bool   `json:"retryable"`
}
type Response struct {
	SchemaVersion int    `json:"schema_version"`
	RequestID     string `json:"request_id"`
	OK            bool   `json:"ok"`
	Result        any    `json:"result,omitempty"`
	Error         *Fault `json:"error,omitempty"`
}

func Fail(id, code, category, stage string, retry bool) Response {
	return Response{SchemaVersion: Version, RequestID: id, OK: false, Error: &Fault{Code: code, Category: category, Stage: stage, Message: code, Retryable: retry}}
}
func Success(id string, result any) Response {
	return Response{SchemaVersion: Version, RequestID: id, OK: true, Result: result}
}
func StrictBytes(data []byte, v any) error {
	d := json.NewDecoder(bytes.NewReader(data))
	d.DisallowUnknownFields()
	if err := d.Decode(v); err != nil {
		return err
	}
	var extra any
	if err := d.Decode(&extra); !errors.Is(err, io.EOF) {
		return errors.New("extra JSON after envelope")
	}
	return nil
}
func Decode(r io.Reader) (Request, error) {
	b, e := io.ReadAll(io.LimitReader(r, MaxEnvelope+1))
	if e != nil {
		return Request{}, e
	}
	if len(b) > MaxEnvelope {
		return Request{}, errors.New("request exceeds size limit")
	}
	var req Request
	if err := StrictBytes(b, &req); err != nil {
		return req, fmt.Errorf("invalid JSON envelope: %w", err)
	}
	if req.SchemaVersion != Version {
		return req, errors.New("unsupported schema version")
	}
	if len(req.RequestID) == 0 || len(req.RequestID) > 80 {
		return req, errors.New("invalid request ID")
	}
	for _, c := range req.RequestID {
		if !(c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z' || c >= '0' && c <= '9' || c == '-' || c == '_') {
			return req, errors.New("invalid request ID")
		}
	}
	if !req.Class.Valid() || len(req.Operation) > 90 || len(req.Operation) == 0 || strings.ContainsAny(req.Operation, " /\\\x00\n") {
		return req, errors.New("invalid operation/class")
	}
	if len(req.Arguments) > 0 && !json.Valid(req.Arguments) {
		return req, errors.New("invalid arguments")
	}
	return req, nil
}
func MarshalResponse(res Response) ([]byte, error) {
	b, e := json.Marshal(res)
	if e != nil {
		return nil, e
	}
	if len(b) > MaxResponse {
		return nil, errors.New("response exceeds limit")
	}
	return append(b, '\n'), nil
}
