// Package control dispatches a finite allowlist of typed backend operations.
package control

import (
	"context"
	"encoding/json"
	"fmt"
	"skybind/internal/protocol"
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
	mu      sync.RWMutex
	entries map[string]entry
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
func (e *Engine) Dispatch(ctx context.Context, req protocol.Request) protocol.Response {
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
	result, err := x.handler(ctx, req.Arguments)
	if err != nil {
		return protocol.Fail(req.RequestID, "operation_failed", "operation", "execute", false)
	}
	return protocol.Success(req.RequestID, result)
}
