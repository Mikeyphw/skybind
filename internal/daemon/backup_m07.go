package daemon

// M7 backup extension: no generic file system bridge or credential export.
// Restores reuse the existing config preview-proof and lifecycle prepare logic.
import (
	"context"
	"encoding/json"
	"errors"
	"skybind/internal/backup"
	"skybind/internal/control"
	"skybind/internal/mounts/config"
	"skybind/internal/offline"
	"skybind/internal/protocol"
	"skybind/internal/uisettings"
)

func RegisterBackup(e *control.Engine, registry *config.Store, prefs *uisettings.Store, pins *offline.Store, apply func([]byte, string) (config.Registry, error)) error {
	if e == nil || registry == nil || prefs == nil || pins == nil || apply == nil {
		return errors.New("backup dependencies unavailable")
	}
	if err := e.Register("backup.export", protocol.Query, func(_ context.Context, raw json.RawMessage) (any, error) {
		if err := emptyArgs(raw); err != nil {
			return nil, err
		}
		snap, err := registry.Snapshot()
		if err != nil {
			return nil, err
		}
		manifest, err := pins.List()
		if err != nil {
			return nil, err
		}
		return backup.Build(snap, prefs.Snapshot(), manifest)
	}); err != nil {
		return err
	}
	type request struct {
		Document backup.Document `json:"document"`
	}
	if err := e.Register("backup.save", protocol.Run, func(_ context.Context, raw json.RawMessage) (any, error) {
		var a struct {
			AcknowledgePublic bool `json:"acknowledge_public"`
		}
		if err := protocol.StrictBytes(raw, &a); err != nil {
			return nil, err
		}
		if !a.AcknowledgePublic {
			return nil, errors.New("public backup export requires confirmation")
		}
		snap, err := registry.Snapshot()
		if err != nil {
			return nil, err
		}
		manifest, err := pins.List()
		if err != nil {
			return nil, err
		}
		doc, err := backup.Build(snap, prefs.Snapshot(), manifest)
		if err != nil {
			return nil, err
		}
		path, err := backup.SaveToDownloads(doc)
		if err != nil {
			return nil, err
		}
		return map[string]any{"path": path, "sha256": doc.SHA256, "mounts": len(doc.Payload.Registry.Mounts), "pin_references_only": len(doc.Payload.PinReferences)}, nil
	}); err != nil {
		return err
	}
	if err := e.Register("backup.preview", protocol.Preview, func(_ context.Context, raw json.RawMessage) (any, error) {
		var a request
		if err := protocol.StrictBytes(raw, &a); err != nil {
			return nil, err
		}
		snap, err := registry.Snapshot()
		if err != nil {
			return nil, err
		}
		candidate, err := backup.Candidate(a.Document, snap.Revision)
		if err != nil {
			return nil, err
		}
		plan, err := registry.Preview(candidate)
		if err != nil {
			return nil, err
		}
		return struct {
			Plan              config.Plan `json:"plan"`
			MountsRestored    int         `json:"mounts_restored"`
			PinReferencesOnly int         `json:"pin_references_only"`
			SettingsIncluded  bool        `json:"settings_included"`
			AllMountsDisabled bool        `json:"all_mounts_disabled"`
			Warning           string      `json:"warning"`
		}{plan, len(a.Document.Payload.Registry.Mounts), len(a.Document.Payload.PinReferences), true, true, "Remote credentials and offline files are not included. Restore disables all mounts; original rclone remotes must be configured separately."}, nil
	}); err != nil {
		return err
	}
	if err := e.Register("backup.restore", protocol.Run, func(_ context.Context, raw json.RawMessage) (any, error) {
		var a struct {
			Document            backup.Document `json:"document"`
			Proof               string          `json:"proof"`
			AcknowledgeDisabled bool            `json:"acknowledge_disabled"`
		}
		if err := protocol.StrictBytes(raw, &a); err != nil {
			return nil, err
		}
		if !a.AcknowledgeDisabled || a.Proof == "" {
			return nil, errors.New("explicit disabled-mount restore confirmation required")
		}
		snap, err := registry.Snapshot()
		if err != nil {
			return nil, err
		}
		candidate, err := backup.Candidate(a.Document, snap.Revision)
		if err != nil {
			return nil, err
		}
		// Existing proof consumption, durable pending recovery and owned mount
		// quiescing are all retained through lifecycle.ApplyConfig.
		return apply(candidate, a.Proof)
	}); err != nil {
		return err
	}
	return nil
}
