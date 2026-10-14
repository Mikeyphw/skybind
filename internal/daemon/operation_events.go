package daemon

import (
	"context"
	"encoding/json"
	"errors"
	"skybind/internal/control"
	"skybind/internal/jobs"
	"skybind/internal/opevents"
	"skybind/internal/protocol"
	"time"
)

// RegisterOperationEvents exposes the additive personal API extension without
// changing the frozen 57-operation contract. Events are readable only through
// the existing same-UID Unix socket or its authenticated WebUI transport.
func RegisterOperationEvents(e *control.Engine, jobsStore *jobs.Store, events *opevents.Store) error {
	if e == nil || events == nil {
		return errors.New("operation events unavailable")
	}
	publish := func(event opevents.Event) { _ = events.Append(event) }
	e.SetEventObserver(publish)
	if jobsStore != nil {
		jobsStore.SetEventObserver(publish)
	}
	return e.Register("operation.events", protocol.Query, func(ctx context.Context, raw json.RawMessage) (any, error) {
		var p struct {
			Cursor      uint64 `json:"cursor"`
			Limit       int    `json:"limit"`
			OperationID string `json:"operation_id"`
			WaitMS      int    `json:"wait_ms"`
		}
		if err := protocol.StrictBytes(raw, &p); err != nil {
			return nil, err
		}
		if p.Limit == 0 {
			p.Limit = 32
		}
		if p.WaitMS < 0 || p.WaitMS > 5000 {
			return nil, errors.New("invalid event wait")
		}
		return events.Poll(ctx, p.Cursor, p.Limit, p.OperationID, time.Duration(p.WaitMS)*time.Millisecond)
	})
}
