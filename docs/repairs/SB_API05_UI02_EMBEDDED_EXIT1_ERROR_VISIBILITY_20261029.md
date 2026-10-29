# SB-API05/UI02 — Embedded WebUI typed-backend error visibility (2026-10-29)

**Source pin:** `bab07e7d9bbbd01a33d77346c128473d5813653a` (UI01 already merged).

## Evidence and bug

The 2026-10-29 installed-device support bundle contained healthy `mount.list`, `runtime.status`, `provider.status`, and `system.capabilities` transactions while repeated `mount.status` calls reported `operation_failed`. The WebUI showed **“Embedded backend exited with status 1”**. The root CLI at `cmd/skybind/main.go` emits structured JSON for a typed rejection and then returns nonzero; `module/webroot/bridge.js` discarded that JSON on a nonzero manager callback. This falsely presented an operation-level denial as a transport failure and hid the backend error code.

## Changes

- Preserve a strictly matching structured `schema_version:1`, `request_id:<exact caller ID>`, `ok:false` and nonempty `error.code` response even if the embedded CLI exited with a nonzero status.
- Continue rejecting mismatched IDs, malformed/non-JSON stdout and nonzero errors without a valid typed denial. Positive (`ok:true`) responses must still have exactly the request ID, and may not be accepted from nonzero CLI exit status.
- No automatic retry, mount start/stop, daemon restart, SELinux change, policy provisioning, or fallback to unverified transports.
- The WebUI's existing `nativeValue`/`result` error presentation remains authoritative; explicit rejection is not silently treated as success.

## Boundaries / evidence requirements

**Delivered:** local bridge repair and isolated regression tests. **Partial:** only a source-simulated KernelSU callback; actual installed WebUI needs retesting. **Open:** why the device's `mount.status` returned `operation_failed` after module installation, real FUSE owner verification and API-05 lifecycle receipt. A patch that changes how errors are displayed is **not** a fix to the underlying mount runtime state.

### Safe device diagnostic (read-only)

```sh
CLI=/data/adb/modules/skybind/system/bin/skybind
su -c "$CLI mount list"
su -c "$CLI mount status safegdrive"
su -c "$CLI mount health safegdrive"
su -c "$CLI runtime-status"
```

For commands that return exit status 1, preserve their JSON stdout. Avoid `purge-state`, restarting the daemon, deleting ownership records or unmounting an existing active mount without independent FUSE/writeback validation.
