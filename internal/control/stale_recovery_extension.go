package control

import "skybind/internal/protocol"

// Operator-only maintenance operations. Intentionally outside the fixed 59-op
// app/WebUI catalog: the WebUI has no route to initiate stale record recovery.
func lookupStaleRecoveryExtension(name string) (CatalogItem, bool) {
	switch name {
	case "mount.stale.preview":
		return CatalogItem{Name: name, OperationClass: protocol.Preview, Description: "Read-only preview for an orphaned mount ownership record", ImplementingOverlay: "API05_STALE_RECORD_R1", WebUIConsumers: "none (root CLI only)", Implemented: true, Cancellation: "not_applicable"}, true
	case "mount.stale.recover":
		return CatalogItem{Name: name, OperationClass: protocol.Run, Description: "Proof-bound explicit archive of a stale mount record, without signaling or mounting", ImplementingOverlay: "API05_STALE_RECORD_R1", WebUIConsumers: "none (root CLI only)", Implemented: true, Cancellation: "not_applicable"}, true
	default:
		return CatalogItem{}, false
	}
}
