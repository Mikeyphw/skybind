# Skybind B3 Android connectivity observer hotfix

## Problem

The physical Android qualification run reported `remote.media.start_rejected` before a job was created, while the local source and root-owned job store were accessible. The separate non-mutating device diagnostic reported `network_fact=unknown`, `no_kernel_default_route_observed`. Skybind's managed jobs use `policy.Evaluate(NetworkMode=any)` and reject unknown connectivity.

## Change

`internal/mounts/policy/android.go` adds a fail-closed fallback for the Android route observer. When the kernel route cannot prove connectivity, Skybind inspects a bounded 1 MiB `dumpsys connectivity` snapshot (2-second timeout, no shell, no log of raw text). The fallback only recognizes a unique, validated, non-VPN active default network with exactly one supported `WIFI` or `CELLULAR` transport. Metering is derived from that same network's capabilities. Unknown, unvalidated, offline, VPN, mixed-transport, duplicate, and incomplete facts remain unknown. All existing resource-policy rules remain unchanged, including Wi-Fi/unmetered restrictions.

The fix is conditional: if this Android ROM omits or redacts the required connectivity-service details, the network class remains unknown and managed transfers remain blocked. Running `network_probe.py` from this bundle before rebuilding identifies whether the ROM exposes evidence required by this fallback without emitting raw network details.

## Validate

`go test ./...`; `go vet ./...`; `GOOS=android GOARCH=arm64 CGO_ENABLED=0 go build ./cmd/skybind`; WebUI parity and device unit tests. Source checks are not physical Android acceptance.

## Device acceptance

1. Run the included read-only network probe and inspect `candidate_network`.
2. Apply the source-bound Devtool overlay. Rebuild and install the module at an intentional maintenance window.
3. Confirm Skybind `policy.status` now reports a supported network value, and that the installed binary hash matches your actual build receipt. Existing mount may have `offline-allowed` policy; the `allowed:true` field alone does not prove job connectivity.
4. Re-run `./devtoolw api-device-readonly` and a uniquely scoped `api-device-disposable` test. Do not reuse the failed test's workspace as a destination. Do not delete queued writeback edits or existing test artifacts.

**Scope:** Only Android network-observer source, unit tests, and documentation. No mount supervisor, FUSE, offline/writeback, remote transfer, storage permission, credential or proof logic is modified. Android device results remain pending.
