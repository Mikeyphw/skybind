package control

import "skybind/internal/protocol"

// Optional personal-project M5 UI extension. The original 57-operation CFS1
// catalog is immutable; these are separately allowlisted, NOT silently added
// to the historical catalog or represented as CFS1-qualified operations.
var offlineExtension = map[string]protocol.Class{
	"offline.list":         protocol.Query,
	"offline.status":       protocol.Query,
	"offline.tasks":        protocol.Query,
	"offline.pin":          protocol.Run,
	"offline.export":       protocol.Run,
	"offline.view.publish": protocol.Run,
	"offline.unpin":        protocol.Run,
	"offline.quota":        protocol.Run,
	"offline.cancel":       protocol.Cancel,
}

func lookupOfflineExtension(name string) (CatalogItem, bool) {
	class, ok := offlineExtension[name]
	if !ok {
		return CatalogItem{}, false
	}
	return CatalogItem{
		Name: name, OperationClass: class,
		Description:         "Optional explicitly scoped M5 read-only offline snapshot operation",
		ImplementingOverlay: "SKYBIND-M5-UI", WebUIConsumers: "Mounts / Offline",
		Cancellation: "operation_specific", ArgumentsSchema: `{"type":"object"}`,
	}, true
}
