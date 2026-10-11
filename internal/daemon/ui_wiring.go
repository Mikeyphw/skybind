package daemon

import (
	"context"
	"encoding/json"
	"skybind/internal/control"
	"skybind/internal/protocol"
	"skybind/internal/uisettings"
)

// RegisterUISettings is called by the privileged daemon only with a verified
// private store. This never grants frontend authority over runtime or mounts.
func RegisterUISettings(e *control.Engine, s *uisettings.Store) error {
	if e == nil || s == nil {
		return nil
	}
	if err := e.Register("ui.settings", protocol.Query, func(_ context.Context, a json.RawMessage) (any, error) {
		if err := emptyArgs(a); err != nil {
			return nil, err
		}
		return s.Snapshot(), nil
	}); err != nil {
		return err
	}
	if err := e.Register("ui.settings.preview", protocol.Preview, func(_ context.Context, a json.RawMessage) (any, error) {
		var v struct {
			Settings uisettings.Settings `json:"settings"`
		}
		if err := protocol.StrictBytes(a, &v); err != nil {
			return nil, err
		}
		return s.Preview(v.Settings)
	}); err != nil {
		return err
	}
	return e.Register("ui.settings.apply", protocol.Run, func(_ context.Context, a json.RawMessage) (any, error) {
		var v struct {
			ExpectedRevision uint64              `json:"expected_revision"`
			Settings         uisettings.Settings `json:"settings"`
			CandidateDigest  string              `json:"candidate_digest"`
			PreviewProof     string              `json:"preview_proof"`
		}
		if err := protocol.StrictBytes(a, &v); err != nil {
			return nil, err
		}
		return s.Apply(v.ExpectedRevision, v.Settings, v.CandidateDigest, v.PreviewProof)
	})
}
