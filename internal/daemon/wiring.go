package daemon

import (
	"context"
	"encoding/json"
	"errors"
	"skybind/internal/control"
	"skybind/internal/journal"
	"skybind/internal/protocol"
	"skybind/internal/runtimeauth"
)

// BaseEngine implements only currently functional capabilities; no future
// operation is advertised as implemented.
func BaseEngine(j *journal.Journal) *control.Engine {
	e := control.New()
	register := func(name string, class protocol.Class, fn control.Handler) {
		if err := e.Register(name, class, fn); err != nil {
			panic(err)
		}
	}
	register("runtime.status", protocol.Query, func(context.Context, json.RawMessage) (any, error) { return runtimeauth.StatusCanonical(), nil })
	register("system.capabilities", protocol.Query, func(context.Context, json.RawMessage) (any, error) { return e.Descriptors(), nil })
	if j != nil {
		register("operation.list", protocol.Query, func(_ context.Context, arg json.RawMessage) (any, error) {
			if len(arg) > 0 && string(arg) != "null" && string(arg) != "{}" {
				return nil, errors.New("unexpected arguments")
			}
			return j.List()
		})
		register("operation.status", protocol.Query, func(_ context.Context, arg json.RawMessage) (any, error) {
			var p struct {
				ID string `json:"id"`
			}
			if err := protocol.StrictBytes(arg, &p); err != nil {
				return nil, err
			}
			return j.Get(p.ID)
		})
		register("operation.cancel", protocol.Cancel, func(_ context.Context, arg json.RawMessage) (any, error) {
			var p struct {
				ID string `json:"id"`
			}
			if err := protocol.StrictBytes(arg, &p); err != nil {
				return nil, err
			}
			return j.Cancel(p.ID)
		})
	}
	return e
}
