// Package featureapi is the versioned, root-authorized Skybind feature surface.
// It NEVER starts a second mount controller or exposes rclone/credential APIs.
package featureapi

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"regexp"
	"skybind/internal/control"
	"skybind/internal/protocol"
	"sort"
)

const Version = 1
const MaxCallBytes = protocol.MaxEnvelope

// This narrow public allowlist is deliberately separate from the much larger
// internal control catalog. All mutations still pass the daemon's journal,
// preview/proof, namespace-ownership and policy gates.
var operations = map[string]protocol.Class{
	"mount.list":                 protocol.Query,
	"mount.status":               protocol.Query,
	"mount.health":               protocol.Query,
	"mount.start.preview":        protocol.Preview,
	"mount.stop.preview":         protocol.Preview,
	"mount.stop.guarded":         protocol.Run,
	"mount.start":                protocol.Run,
	"mount.stop":                 protocol.Run,
	"mount.restart":              protocol.Run,
	"mount.reconcile":            protocol.Reconcile,
	"namespace.inspect":          protocol.Query,
	"namespace.preview":          protocol.Preview,
	"namespace.apply":            protocol.Run,
	"namespace.rollback.preview": protocol.Preview,
	"namespace.rollback":         protocol.Run,
	"namespace.reconcile":        protocol.Reconcile,
	"operation.status":           protocol.Query,
	"operation.events":           protocol.Query,
}

func ClassFor(operation string) (protocol.Class, bool) {
	cls, ok := operations[operation]
	return cls, ok
}

type Capability struct {
	Operation       string         `json:"operation"`
	Class           protocol.Class `json:"class"`
	Implemented     bool           `json:"implemented"`
	PreviewRequired bool           `json:"preview_required"`
}
type Capabilities struct {
	APIVersion      int          `json:"api_version"`
	ProtocolVersion int          `json:"protocol_version"`
	Transport       string       `json:"transport"`
	Authorization   string       `json:"authorization"`
	Operations      []Capability `json:"operations"`
}

func Discover(descriptors []control.Descriptor) Capabilities {
	found := make(map[string]protocol.Class, len(descriptors))
	for _, d := range descriptors {
		if d.Implemented {
			found[d.Operation] = d.Class
		}
	}
	names := make([]string, 0, len(operations))
	for k := range operations {
		names = append(names, k)
	}
	sort.Strings(names)
	caps := Capabilities{APIVersion: Version, ProtocolVersion: protocol.Version,
		Transport: "private_same_uid_unix_v1", Authorization: "root_only", Operations: make([]Capability, 0, len(names))}
	for _, name := range names {
		cl := operations[name]
		caps.Operations = append(caps.Operations, Capability{Operation: name, Class: cl,
			Implemented:     found[name] == cl,
			PreviewRequired: name == "mount.start" || name == "mount.stop.guarded" || name == "namespace.apply" || name == "namespace.rollback"})
	}
	return caps
}

type Call struct {
	Operation  string          `json:"operation,omitempty"`
	APIVersion int             `json:"api_version"`
	RequestID  string          `json:"request_id"`
	Arguments  json.RawMessage `json:"arguments"`
}

var requestID = regexp.MustCompile(`^[A-Za-z0-9_-]{1,80}$`)

// DecodeCall requires a caller-supplied stable request_id for lost-reply
// reconciliation. No request can choose a transport, class, shell or UID.
func DecodeCall(r io.Reader) (Call, error) {
	var req Call
	buf, err := io.ReadAll(io.LimitReader(r, MaxCallBytes+1))
	if err != nil {
		return req, err
	}
	if len(buf) == 0 || len(buf) > MaxCallBytes {
		return req, errors.New("feature_request_size")
	}
	if err = checkTopLevel(buf); err != nil {
		return req, err
	}
	if err = protocol.StrictBytes(buf, &req); err != nil {
		return req, errors.New("feature_invalid_envelope")
	}
	if req.APIVersion != Version {
		return req, errors.New("feature_version_unsupported")
	}
	if !requestID.MatchString(req.RequestID) {
		return req, errors.New("feature_request_id_invalid")
	}
	if len(req.Arguments) == 0 {
		return req, errors.New("feature_arguments_required")
	}
	if err = rejectDuplicateJSON(req.Arguments); err != nil {
		return req, err
	}
	var args map[string]json.RawMessage
	if err = protocol.StrictBytes(req.Arguments, &args); err != nil || args == nil {
		return req, errors.New("feature_arguments_object_required")
	}
	if req.Operation != "" {
		if _, ok := ClassFor(req.Operation); !ok {
			return req, errors.New("feature_operation_not_allowed")
		}
	}
	return req, nil
}

// Detect duplicate top-level keys before unmarshalling (Unmarshal alone uses
// last-wins semantics and would make request identity ambiguous).
func checkTopLevel(data []byte) error {
	d := json.NewDecoder(bytes.NewReader(data))
	first, err := d.Token()
	if err != nil || first != json.Delim('{') {
		return errors.New("feature_object_required")
	}
	seen := map[string]bool{}
	for d.More() {
		k, err := d.Token()
		if err != nil {
			return errors.New("feature_invalid_key")
		}
		name, ok := k.(string)
		if !ok || seen[name] {
			return errors.New("feature_duplicate_key")
		}
		seen[name] = true
		var raw json.RawMessage
		if err = d.Decode(&raw); err != nil {
			return errors.New("feature_invalid_value")
		}
	}
	end, err := d.Token()
	if err != nil || end != json.Delim('}') {
		return errors.New("feature_invalid_object")
	}
	var unused json.RawMessage
	if err = d.Decode(&unused); err != io.EOF {
		return errors.New("feature_trailing_data")
	}
	if !seen["api_version"] || !seen["request_id"] || !seen["arguments"] {
		return errors.New("feature_missing_field")
	}
	return nil
}

// rejectDuplicateJSON walks nested argument structures so an attacker cannot
// cause an ambiguous "proof" or "name" to be accepted by last-wins decoding.
func rejectDuplicateJSON(data []byte) error {
	d := json.NewDecoder(bytes.NewReader(data))
	var value func(int) error
	value = func(depth int) error {
		if depth > 40 {
			return errors.New("feature_json_depth")
		}
		tok, err := d.Token()
		if err != nil {
			return errors.New("feature_json_invalid")
		}
		switch tok {
		case json.Delim('{'):
			seen := map[string]bool{}
			for d.More() {
				t, e := d.Token()
				if e != nil {
					return errors.New("feature_json_key")
				}
				key, ok := t.(string)
				if !ok || seen[key] {
					return errors.New("feature_json_duplicate_key")
				}
				seen[key] = true
				if e = value(depth + 1); e != nil {
					return e
				}
			}
			end, e := d.Token()
			if e != nil || end != json.Delim('}') {
				return errors.New("feature_json_object")
			}
		case json.Delim('['):
			for d.More() {
				if e := value(depth + 1); e != nil {
					return e
				}
			}
			end, e := d.Token()
			if e != nil || end != json.Delim(']') {
				return errors.New("feature_json_array")
			}
		case json.Delim('}'), json.Delim(']'):
			return errors.New("feature_json_delimiter")
		}
		return nil
	}
	if e := value(0); e != nil {
		return e
	}
	_, e := d.Token()
	if e != io.EOF {
		return errors.New("feature_json_trailing")
	}
	return nil
}
