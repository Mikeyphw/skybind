package control

import (
	"bytes"
	_ "embed"
	"encoding/json"
	"errors"
	"fmt"
	"skybind/internal/protocol"
	"sort"
	"sync"
)

//go:embed operations.json
var catalogBytes []byte

// CatalogItem retains every planned UI operation but truthfully distinguishes
// registered handlers from future work. The static copy is audited against the
// canonical docs/contracts/typed-operations.json by Devtool.
type CatalogItem struct {
	Name                string         `json:"name"`
	OperationClass      protocol.Class `json:"operation_class"`
	Description         string         `json:"description"`
	ImplementingOverlay string         `json:"implementing_overlay"`
	WebUIConsumers      string         `json:"webui_consumers"`
	Implemented         bool           `json:"implemented"`
	Cancellation        string         `json:"cancellation"`
	ArgumentsSchema     string         `json:"arguments_schema"`
}
type ProtocolRange struct {
	Min int `json:"min"`
	Max int `json:"max"`
}
type CatalogSnapshot struct {
	Protocol        ProtocolRange `json:"protocol"`
	SchemaVersion   int           `json:"schema_version"`
	ProtocolVersion int           `json:"protocol_version"`
	Total           int           `json:"total"`
	Operations      []CatalogItem `json:"operations"`
}

var catalogOnce sync.Once
var frozen CatalogSnapshot
var catalogErr error

func loadCatalog() (CatalogSnapshot, error) {
	catalogOnce.Do(func() {
		var file struct {
			SchemaVersion int           `json:"schema_version"`
			Product       string        `json:"product"`
			Total         int           `json:"total"`
			Operations    []CatalogItem `json:"operations"`
		}
		d := json.NewDecoder(bytes.NewReader(catalogBytes))
		d.DisallowUnknownFields()
		if err := d.Decode(&file); err != nil {
			catalogErr = err
			return
		}
		if file.SchemaVersion != 1 || file.Total != 59 || len(file.Operations) != 59 {
			catalogErr = errors.New("invalid canonical API catalog size/schema")
			return
		}
		seen := map[string]bool{}
		for _, v := range file.Operations {
			if v.Name == "" || !v.OperationClass.Valid() || seen[v.Name] || v.ImplementingOverlay == "" || v.WebUIConsumers == "" {
				catalogErr = errors.New("invalid canonical API descriptor")
				return
			}
			seen[v.Name] = true
		}
		frozen = CatalogSnapshot{SchemaVersion: 1, Protocol: ProtocolRange{protocol.Version, protocol.Version}, ProtocolVersion: protocol.Version, Total: file.Total, Operations: file.Operations}
	})
	return frozen, catalogErr
}
func SchemaForOperation(name string) string {
	switch name {
	case "operation.status", "operation.cancel":
		return `{"type":"object","required":["id"],"additionalProperties":false}`
	case "config.validate", "config.preview":
		return `{"type":"object","required":["candidate"],"additionalProperties":false}`
	case "config.apply":
		return `{"type":"object","required":["candidate","proof"],"additionalProperties":false}`
	case "config.rollback":
		return `{"type":"object","required":["proof"],"additionalProperties":false}`
	default:
		return `{"type":"object","additionalProperties":false}`
	}
}
func Lookup(name string) (CatalogItem, bool) {
	if v, ok := lookupStaleRecoveryExtension(name); ok {
		return v, true
	}
	if v, ok := lookupOfflineExtension(name); ok {
		return v, true
	}
	c, err := loadCatalog()
	if err != nil {
		return CatalogItem{}, false
	}
	if name == "system.capabilities" {
		return CatalogItem{Name: name, OperationClass: protocol.Query, Description: "Versioned capability discovery", Implemented: true, Cancellation: "not_applicable", ArgumentsSchema: SchemaForOperation(name)}, true
	}
	for _, a := range c.Operations {
		if a.Name == name {
			return a, true
		}
	}
	return CatalogItem{}, false
}
func (e *Engine) Catalog() (CatalogSnapshot, error) {
	c, err := loadCatalog()
	if err != nil {
		return c, err
	}
	e.mu.RLock()
	defer e.mu.RUnlock()
	result := CatalogSnapshot{SchemaVersion: 1, Protocol: ProtocolRange{protocol.Version, protocol.Version}, ProtocolVersion: protocol.Version, Total: c.Total, Operations: make([]CatalogItem, 0, len(c.Operations))}
	for _, a := range c.Operations {
		a.ArgumentsSchema = SchemaForOperation(a.Name)
		if entry, ok := e.entries[a.Name]; ok {
			if entry.descriptor.Class != a.OperationClass {
				return result, fmt.Errorf("operation class drift %s", a.Name)
			}
			a.Implemented = true
		}
		if a.OperationClass == protocol.Run || a.OperationClass == protocol.Cancel || a.OperationClass == protocol.Reconcile {
			a.Cancellation = "operation_specific"
		} else {
			a.Cancellation = "not_applicable"
		}
		result.Operations = append(result.Operations, a)
	}
	sort.Slice(result.Operations, func(i, j int) bool { return result.Operations[i].Name < result.Operations[j].Name })
	return result, nil
}
