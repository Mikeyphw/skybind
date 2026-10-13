package control

import "skybind/internal/protocol"

// Optional personal-project M5 UI extension. The original 57-operation CFS1
// catalog is immutable; these are separately allowlisted, NOT silently added
// to the historical catalog or represented as CFS1-qualified operations.
var offlineExtension = map[string]protocol.Class{
	"backup.export":             protocol.Query,
	"backup.save":               protocol.Run,
	"backup.preview":            protocol.Preview,
	"backup.restore":            protocol.Run,
	"offline.list":              protocol.Query,
	"offline.status":            protocol.Query,
	"offline.tasks":             protocol.Query,
	"offline.pin":               protocol.Run,
	"offline.export":            protocol.Run,
	"offline.view.publish":      protocol.Run,
	"offline.unpin":             protocol.Run,
	"offline.quota":             protocol.Run,
	"offline.cancel":            protocol.Cancel,
	"offline.write.list":        protocol.Query,
	"offline.write.check":       protocol.Query,
	"offline.write.draft":       protocol.Run,
	"offline.write.stage":       protocol.Run,
	"offline.write.upload-copy": protocol.Run,
	"offline.write.review":      protocol.Query,
	"offline.write.reconcile":   protocol.Run,
	"offline.write.auto-review": protocol.Run,
}

func lookupOfflineExtension(name string) (CatalogItem, bool) {
	class, ok := offlineExtension[name]
	if !ok {
		return CatalogItem{}, false
	}
	return CatalogItem{
		Name: name, OperationClass: class,
		Description:         "Optional allowlisted offline or M7 personal configuration backup operation",
		ImplementingOverlay: "SKYBIND-M5-UI", WebUIConsumers: "Mounts / Offline",
		Cancellation: "operation_specific", ArgumentsSchema: `{"type":"object"}`,
	}, true
}
