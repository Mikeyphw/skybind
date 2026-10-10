package daemon

import (
	"context"
	"encoding/json"
	"errors"
	"skybind/internal/control"
	"skybind/internal/journal"
	"skybind/internal/mounts/config"
	"skybind/internal/protocol"
	"skybind/internal/runtimeauth"
)

func emptyArgs(raw json.RawMessage) error {
	if len(raw) == 0 {
		return nil
	}
	var x map[string]json.RawMessage
	if err := protocol.StrictBytes(raw, &x); err != nil {
		return err
	}
	if x == nil || len(x) != 0 {
		return errors.New("expected an empty object")
	}
	return nil
}
func BaseEngine(j *journal.Journal) *control.Engine { return EngineWithConfig(j, nil) }

// EngineWithConfig is the only daemon registration point for the current
// implemented feature set. No nonfunctional operation is registered.
func EngineWithConfig(j *journal.Journal, s *config.Store) *control.Engine {
	e := control.New()
	register := func(name string, class protocol.Class, fn control.Handler) {
		if err := e.Register(name, class, fn); err != nil {
			panic(err)
		}
	}
	register("runtime.status", protocol.Query, func(_ context.Context, a json.RawMessage) (any, error) {
		if err := emptyArgs(a); err != nil {
			return nil, err
		}
		return runtimeauth.StatusCanonical(), nil
	})
	register("system.capabilities", protocol.Query, func(_ context.Context, a json.RawMessage) (any, error) {
		if err := emptyArgs(a); err != nil {
			return nil, err
		}
		return e.Catalog()
	})
	if j != nil {
		register("operation.list", protocol.Query, func(_ context.Context, a json.RawMessage) (any, error) {
			if err := emptyArgs(a); err != nil {
				return nil, err
			}
			return j.List()
		})
		register("operation.status", protocol.Query, func(_ context.Context, a json.RawMessage) (any, error) {
			var p struct {
				ID string `json:"id"`
			}
			if err := protocol.StrictBytes(a, &p); err != nil {
				return nil, err
			}
			if p.ID == "" {
				return nil, errors.New("empty id")
			}
			return j.Get(p.ID)
		})
		register("operation.cancel", protocol.Cancel, func(_ context.Context, a json.RawMessage) (any, error) {
			var p struct {
				ID string `json:"id"`
			}
			if err := protocol.StrictBytes(a, &p); err != nil {
				return nil, err
			}
			if p.ID == "" {
				return nil, errors.New("empty id")
			}
			return j.Cancel(p.ID)
		})
	}
	if s != nil {
		register("config.snapshot", protocol.Query, func(_ context.Context, a json.RawMessage) (any, error) {
			if err := emptyArgs(a); err != nil {
				return nil, err
			}
			return s.Snapshot()
		})
		register("config.previous", protocol.Query, func(_ context.Context, a json.RawMessage) (any, error) {
			if err := emptyArgs(a); err != nil {
				return nil, err
			}
			return s.Previous()
		})
		decodeCandidate := func(a json.RawMessage) ([]byte, error) {
			var p struct {
				Candidate json.RawMessage `json:"candidate"`
			}
			if err := protocol.StrictBytes(a, &p); err != nil {
				return nil, err
			}
			if len(p.Candidate) == 0 {
				return nil, errors.New("missing candidate")
			}
			return p.Candidate, nil
		}
		register("config.validate", protocol.Query, func(_ context.Context, a json.RawMessage) (any, error) {
			c, err := decodeCandidate(a)
			if err != nil {
				return nil, err
			}
			return s.Validate(c)
		})
		register("config.preview", protocol.Preview, func(_ context.Context, a json.RawMessage) (any, error) {
			c, err := decodeCandidate(a)
			if err != nil {
				return nil, err
			}
			return s.Preview(c)
		})
		register("config.apply", protocol.Run, func(_ context.Context, a json.RawMessage) (any, error) {
			var p struct {
				Candidate json.RawMessage `json:"candidate"`
				Proof     string          `json:"proof"`
			}
			if err := protocol.StrictBytes(a, &p); err != nil {
				return nil, err
			}
			if len(p.Candidate) == 0 || p.Proof == "" {
				return nil, errors.New("missing candidate/proof")
			}
			return s.Apply(p.Candidate, p.Proof)
		})
		register("config.rollback.preview", protocol.Preview, func(_ context.Context, a json.RawMessage) (any, error) {
			if err := emptyArgs(a); err != nil {
				return nil, err
			}
			return s.RollbackPreview()
		})
		register("config.rollback", protocol.Run, func(_ context.Context, a json.RawMessage) (any, error) {
			var p struct {
				Proof string `json:"proof"`
			}
			if err := protocol.StrictBytes(a, &p); err != nil {
				return nil, err
			}
			if p.Proof == "" {
				return nil, errors.New("missing proof")
			}
			return s.Rollback(p.Proof)
		})
	}
	return e
}
