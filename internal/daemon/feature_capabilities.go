package daemon

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"os"
	"skybind/internal/control"
	"skybind/internal/featureapi"
	"skybind/internal/journal"
	"skybind/internal/protocol"
	"sync"
)

// RegisterFeatureCapabilities is called after other daemon extensions so the
// versioned public snapshot reflects only actually registered operations.
// It does not start a separate socket, issue grants or bypass same-UID checks.
func RegisterFeatureCapabilities(engine *control.Engine, j *journal.Journal) error {
	if engine == nil {
		return errors.New("feature_engine_missing")
	}
	if err := engine.Register("feature.capabilities", protocol.Query,
		func(_ context.Context, raw json.RawMessage) (any, error) {
			if err := emptyArgs(raw); err != nil {
				return nil, err
			}
			return featureapi.Discover(engine.Descriptors()), nil
		}); err != nil {
		return err
	}
	var mu sync.Mutex // serialize feature mutations across accepted connections
	return engine.Register("feature.execute", protocol.Query,
		func(ctx context.Context, raw json.RawMessage) (any, error) {
			call, err := featureapi.DecodeCall(bytes.NewReader(raw))
			if err != nil || call.Operation == "" {
				return nil, errors.New("invalid_feature_call")
			}
			cls, ok := featureapi.ClassFor(call.Operation)
			if !ok {
				return nil, errors.New("feature_operation_denied")
			}
			request := protocol.Request{SchemaVersion: protocol.Version, RequestID: call.RequestID,
				Operation: call.Operation, Class: cls, Arguments: call.Arguments}
			if cls == protocol.Run || cls == protocol.Reconcile || cls == protocol.Cancel {
				if j == nil {
					return protocol.Fail(call.RequestID, "feature_journal_unavailable", "storage", "execute", false), nil
				}
				mu.Lock()
				defer mu.Unlock()
				_, err = j.ByRequest(call.RequestID)
				if err == nil {
					return protocol.Fail(call.RequestID, "duplicate_request_use_operation_status", "state", "reconcile", false), nil
				}
				if !os.IsNotExist(err) {
					return protocol.Fail(call.RequestID, "feature_journal_unavailable", "storage", "reconcile", false), nil
				}
			}
			return engine.Dispatch(ctx, request), nil
		})

}

// RegisterFeatureCapabilities only runs in the ordinary private daemon; the
// feature executor is not an R1 broker or external Binder/socket endpoint.
