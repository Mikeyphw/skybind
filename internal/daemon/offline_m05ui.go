package daemon

import (
	"context"
	"encoding/json"
	"errors"
	"skybind/internal/control"
	"skybind/internal/offline"
	"skybind/internal/protocol"
)

// RegisterOffline adds only the explicitly reviewed M5 operations to the same
// peer-credential-checked daemon. The embedded/standalone WebUI transports keep
// their existing authentication and CSRF protections; no direct shell bridge.
func RegisterOffline(e *control.Engine, tasks *offline.TaskManager, store *offline.Store) error {
	if e == nil || tasks == nil || store == nil {
		return errors.New("offline unavailable")
	}
	register := func(name string, class protocol.Class, h control.Handler) error { return e.Register(name, class, h) }
	if err := register("offline.list", protocol.Query, func(ctx context.Context, raw json.RawMessage) (any, error) {
		if err := emptyArgs(raw); err != nil {
			return nil, err
		}
		if tasks.Busy() {
			return nil, errors.New("offline_busy")
		}
		return store.List()
	}); err != nil {
		return err
	}
	if err := register("offline.tasks", protocol.Query, func(ctx context.Context, raw json.RawMessage) (any, error) {
		if err := emptyArgs(raw); err != nil {
			return nil, err
		}
		return map[string]any{"tasks": tasks.Tasks()}, nil
	}); err != nil {
		return err
	}
	type selection struct {
		Mount string `json:"mount"`
		Path  string `json:"path"`
	}
	decode := func(raw json.RawMessage) (selection, error) {
		var a selection
		err := protocol.StrictBytes(raw, &a)
		return a, err
	}
	if err := register("offline.status", protocol.Query, func(ctx context.Context, raw json.RawMessage) (any, error) {
		a, err := decode(raw)
		if err != nil {
			return nil, err
		}
		if tasks.Busy() {
			return nil, errors.New("offline_busy")
		}
		return store.Status(ctx, a.Mount, a.Path, false)
	}); err != nil {
		return err
	}
	if err := register("offline.pin", protocol.Run, func(ctx context.Context, raw json.RawMessage) (any, error) {
		var a struct {
			Mount     string `json:"mount"`
			Path      string `json:"path"`
			Recursive bool   `json:"recursive"`
		}
		if err := protocol.StrictBytes(raw, &a); err != nil {
			return nil, err
		}
		kind := "pin"
		if a.Recursive {
			kind = "pin-dir"
		}
		return tasks.Start(kind, a.Mount, a.Path)
	}); err != nil {
		return err
	}
	if err := register("offline.view.publish", protocol.Run, func(ctx context.Context, raw json.RawMessage) (any, error) {
		var a struct {
			Mount string `json:"mount"`
		}
		if err := protocol.StrictBytes(raw, &a); err != nil {
			return nil, err
		}
		return tasks.Start("view", a.Mount, "")
	}); err != nil {
		return err
	}
	if err := register("offline.export", protocol.Run, func(ctx context.Context, raw json.RawMessage) (any, error) {
		a, err := decode(raw)
		if err != nil {
			return nil, err
		}
		return tasks.Start("export", a.Mount, a.Path)
	}); err != nil {
		return err
	}
	if err := register("offline.unpin", protocol.Run, func(ctx context.Context, raw json.RawMessage) (any, error) {
		a, err := decode(raw)
		if err != nil {
			return nil, err
		}
		if tasks.Busy() {
			return nil, errors.New("offline_busy")
		}
		return map[string]bool{"unpinned": true}, store.Unpin(a.Mount, a.Path)
	}); err != nil {
		return err
	}
	if err := register("offline.quota", protocol.Run, func(ctx context.Context, raw json.RawMessage) (any, error) {
		var a struct {
			GiB int64 `json:"gib"`
		}
		if err := protocol.StrictBytes(raw, &a); err != nil {
			return nil, err
		}
		if a.GiB < 1 || a.GiB > 64 {
			return nil, errors.New("offline_invalid_quota")
		}
		if tasks.Busy() {
			return nil, errors.New("offline_busy")
		}
		if err := store.Quota(a.GiB << 30); err != nil {
			return nil, err
		}
		return map[string]int64{"quota_gib": a.GiB}, nil
	}); err != nil {
		return err
	}
	// M6 is opt-in. Editing uses only fixed private/Downloads paths;
	// uploading NEVER targets the original remote name, even on conflicts.
	if err := register("offline.write.list", protocol.Query, func(ctx context.Context, raw json.RawMessage) (any, error) {
		if err := emptyArgs(raw); err != nil {
			return nil, err
		}
		if tasks.Busy() {
			return nil, errors.New("offline_busy")
		}
		return store.Edits()
	}); err != nil {
		return err
	}
	if err := register("offline.write.check", protocol.Query, func(ctx context.Context, raw json.RawMessage) (any, error) {
		var a struct {
			ID string `json:"id"`
		}
		if err := protocol.StrictBytes(raw, &a); err != nil {
			return nil, err
		}
		if tasks.Busy() {
			return nil, errors.New("offline_busy")
		}
		return store.CheckEdit(ctx, a.ID)
	}); err != nil {
		return err
	}
	if err := register("offline.write.draft", protocol.Run, func(ctx context.Context, raw json.RawMessage) (any, error) {
		a, err := decode(raw)
		if err != nil {
			return nil, err
		}
		return tasks.Start("write-draft", a.Mount, a.Path)
	}); err != nil {
		return err
	}
	if err := register("offline.write.stage", protocol.Run, func(ctx context.Context, raw json.RawMessage) (any, error) {
		a, err := decode(raw)
		if err != nil {
			return nil, err
		}
		return tasks.Start("write-stage", a.Mount, a.Path)
	}); err != nil {
		return err
	}
	if err := register("offline.write.upload-copy", protocol.Run, func(ctx context.Context, raw json.RawMessage) (any, error) {
		var a struct {
			ID          string `json:"id"`
			Acknowledge bool   `json:"acknowledge"`
		}
		if err := protocol.StrictBytes(raw, &a); err != nil {
			return nil, err
		}
		if !a.Acknowledge {
			return nil, errors.New("explicit_separate_copy_confirmation_required")
		}
		if tasks.Busy() {
			return nil, errors.New("offline_busy")
		}
		j, err := store.Edits()
		if err != nil {
			return nil, err
		}
		for _, edit := range j.Edits {
			if edit.ID == a.ID && edit.State == "QUEUED" {
				return tasks.Start("write-upload-copy", edit.Mount, a.ID)
			}
		}
		return nil, errors.New("offline_edit_not_queued")
	}); err != nil {
		return err
	}
	// M6B: read-only metadata review of the existing private edit journal.
	// Auto-review only opts into bounded checks on reconnect; no uploads occur.
	if err := register("offline.write.review", protocol.Query, func(ctx context.Context, raw json.RawMessage) (any, error) {
		if err := emptyArgs(raw); err != nil {
			return nil, err
		}
		if tasks.Busy() {
			return nil, errors.New("offline_busy")
		}
		return store.ReviewStatus()
	}); err != nil {
		return err
	}
	if err := register("offline.write.auto-review", protocol.Run, func(ctx context.Context, raw json.RawMessage) (any, error) {
		var a struct {
			Enabled *bool `json:"enabled"`
		}
		if err := protocol.StrictBytes(raw, &a); err != nil {
			return nil, err
		}
		if a.Enabled == nil {
			return nil, errors.New("offline_auto_review_confirmation_required")
		}
		if tasks.Busy() {
			return nil, errors.New("offline_busy")
		}
		return store.SetReviewAuto(*a.Enabled)
	}); err != nil {
		return err
	}
	if err := register("offline.write.reconcile", protocol.Run, func(ctx context.Context, raw json.RawMessage) (any, error) {
		var a struct {
			Mount string `json:"mount"`
		}
		if err := protocol.StrictBytes(raw, &a); err != nil {
			return nil, err
		}
		if a.Mount == "" {
			return nil, errors.New("offline_review_mount_required")
		}
		return tasks.Start("write-review", a.Mount, "")
	}); err != nil {
		return err
	}
	return register("offline.cancel", protocol.Cancel, func(ctx context.Context, raw json.RawMessage) (any, error) {
		var a struct {
			ID string `json:"id"`
		}
		if err := protocol.StrictBytes(raw, &a); err != nil {
			return nil, err
		}
		if err := tasks.Cancel(a.ID); err != nil {
			return nil, err
		}
		return map[string]bool{"cancel_requested": true}, nil
	})
}
