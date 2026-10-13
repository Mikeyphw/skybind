// Package control dispatches a finite allowlist of typed backend operations.
package control

import (
	"context"
	"encoding/json"
	"fmt"
	"skybind/internal/journal"
	"skybind/internal/protocol"
	"strings"
	"sync"
)

type Handler func(context.Context, json.RawMessage) (any, error)
type Descriptor struct {
	Operation   string         `json:"operation"`
	Class       protocol.Class `json:"class"`
	Implemented bool           `json:"implemented"`
}
type entry struct {
	descriptor Descriptor
	handler    Handler
}
type Engine struct {
	mu           sync.RWMutex
	entries      map[string]entry
	audit        func(string, string)
	failureAudit func(string, string)
	journal      *journal.Journal
}

func New() *Engine { return &Engine{entries: make(map[string]entry)} }
func (e *Engine) Register(name string, class protocol.Class, fn Handler) error {
	if name == "" || !class.Valid() || fn == nil {
		return fmt.Errorf("invalid operation descriptor")
	}
	known, ok := Lookup(name)
	if !ok || known.OperationClass != class {
		return fmt.Errorf("operation absent from canonical catalog or wrong class: %s", name)
	}
	e.mu.Lock()
	defer e.mu.Unlock()
	if _, ok := e.entries[name]; ok {
		return fmt.Errorf("duplicate operation")
	}
	e.entries[name] = entry{Descriptor{name, class, true}, fn}
	return nil
}

// SetJournal installs the durable mutation boundary. Failed reservations block effects.
func (e *Engine) SetJournal(j *journal.Journal) { e.mu.Lock(); defer e.mu.Unlock(); e.journal = j }

// SetAudit attaches a bounded outcomes-only observer; it receives no raw arguments.
func (e *Engine) SetAudit(fn func(operation, outcome string)) {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.audit = fn
}

// SetFailureAudit records only allowlisted, non-secret failure categories.
// Raw handler errors and request arguments must never be written to WebUI logs.
func (e *Engine) SetFailureAudit(fn func(operation, reason string)) {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.failureAudit = fn
}

// safeOperationReason intentionally uses a closed vocabulary. Error messages
// from providers, configurations, and arbitrary filesystem paths can contain
// credentials; they must not be forwarded to an embedded WebUI.
func safeOperationReason(operation string, err error) string {
	if err == nil || operation != "mount.start" && operation != "mount.restart" && operation != "mount.stop" {
		return "operation_failed"
	}
	const prefix = "FUSE readiness/mount identity not observed ("
	if strings.HasPrefix(err.Error(), prefix) && strings.HasSuffix(err.Error(), ")") {
		category := strings.TrimSuffix(strings.TrimPrefix(err.Error(), prefix), ")")
		switch category {
		case "provider_permission_denied", "fuse_device_unavailable", "mountpoint_not_empty", "mountpoint_busy", "provider_unsupported_option", "fuse_helper_unavailable", "provider_remote_failure", "provider_stderr_unclassified", "provider_no_stderr_observed", "provider_diagnostics_unavailable":
			return err.Error()
		}
	}
	switch err.Error() {
	case "writeback_unavailable", "writeback_timeout", "writeback_cancelled", "writeback_errors",
		"FUSE readiness/mount identity not observed",
		"could not prove child process ownership",
		"static runtime integrity unverified",
		"destination contains link/non-directory",
		"invalid destination",
		"stale owned process requires recovery",
		"mount disabled",
		"source mount not verified running":
		return err.Error()
	default:
		return "mount failed; internal cause unavailable (provider stderr not captured)"
	}
}

func (e *Engine) Descriptors() []Descriptor {
	e.mu.RLock()
	defer e.mu.RUnlock()
	var a []Descriptor
	for _, x := range e.entries {
		a = append(a, x.descriptor)
	}
	// Stable machine-facing order is essential for UI and CLI parity.
	sortDescriptors(a)
	return a
}
func sortDescriptors(a []Descriptor) {
	for i := 1; i < len(a); i++ {
		for j := i; j > 0 && a[j].Operation < a[j-1].Operation; j-- {
			a[j], a[j-1] = a[j-1], a[j]
		}
	}
}
func (e *Engine) Dispatch(ctx context.Context, req protocol.Request) (response protocol.Response) {
	defer func() {
		e.mu.RLock()
		fn := e.audit
		e.mu.RUnlock()
		if fn != nil {
			outcome := "ok"
			if !response.OK && response.Error != nil {
				outcome = response.Error.Code
			}
			fn(req.Operation, outcome)
		}
	}()
	if req.SchemaVersion != protocol.Version {
		return protocol.Fail(req.RequestID, "unsupported_version", "protocol", "dispatch", false)
	}
	e.mu.RLock()
	x, ok := e.entries[req.Operation]
	e.mu.RUnlock()
	if !ok {
		if item, known := Lookup(req.Operation); known {
			if item.OperationClass != req.Class {
				return protocol.Fail(req.RequestID, "class_mismatch", "authorization", "dispatch", false)
			}
			return protocol.Fail(req.RequestID, "not_implemented", "capability", "dispatch", false)
		}
		return protocol.Fail(req.RequestID, "unknown_operation", "authorization", "dispatch", false)
	}
	if x.descriptor.Class != req.Class {
		return protocol.Fail(req.RequestID, "class_mismatch", "authorization", "dispatch", false)
	}
	var record journal.Record
	var store *journal.Journal
	if req.Class == protocol.Run || req.Class == protocol.Reconcile || req.Class == protocol.Cancel {
		e.mu.RLock()
		store = e.journal
		e.mu.RUnlock()
		if store != nil {
			var errorStart error
			record, errorStart = store.StartRequest(req.Operation, req.RequestID)
			if errorStart != nil {
				return protocol.Fail(req.RequestID, "journal_unavailable", "storage", "reserve", false)
			}
		}
	}
	result, err := x.handler(ctx, req.Arguments)
	if store != nil {
		if err != nil {
			record.State = journal.Failed
			record.Stage = "handler_failed"
			record.ErrorCode = "operation_failed"
		} else {
			record.State = journal.Succeeded
			record.Stage = "handler_returned"
			// A job launch returns RUNNING, not a terminal transfer outcome.
			if req.Operation == "job.run" {
				var run struct {
					ID    string `json:"id"`
					State string `json:"state"`
				}
				if b, e := json.Marshal(result); e == nil && json.Unmarshal(b, &run) == nil && run.State == "RUNNING" && len(run.ID) == 32 {
					record.RunID = run.ID
					record.Stage = "job_claimed_not_finished"
				}
			}
		}
		record.Cancellable = false
		if updateErr := store.Update(record); updateErr != nil {
			return protocol.Fail(req.RequestID, "journal_finalize_failed", "storage", "finalize", false)
		}
	}
	if err != nil {
		reason := safeOperationReason(req.Operation, err)
		e.mu.RLock()
		notify := e.failureAudit
		e.mu.RUnlock()
		if notify != nil && (req.Operation == "mount.start" || req.Operation == "mount.restart" || req.Operation == "mount.stop") {
			notify(req.Operation, reason)
		}
		failure := protocol.Fail(req.RequestID, "operation_failed", "operation", "execute", false)
		if failure.Error != nil && reason != "operation_failed" {
			failure.Error.Message = reason
		}
		return failure
	}
	return protocol.Success(req.RequestID, result)
}
