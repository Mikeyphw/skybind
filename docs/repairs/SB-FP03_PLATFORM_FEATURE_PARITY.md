# SB-FP03 — Platform feature parity (source implementation)

## Scope
- Android metering from bounded system connectivity evidence for the **active default network**, not all Wi-Fi links; ambiguous evidence stays unknown
- Network settling starts on observed daemon-lifetime state changes; no synthetic one-hour uptime
- Read-only, non-authoritative VFS recommendations based on RAM and cache-free-space facts, with original `vfs.profiles` array preserved
- Actionable Doctor probes for private mount registry, job registry, remotes, RC storage, namespace inspectability, root manager, and static WebUI assets; no device-ready claims without device evidence
- Namespace classifier rejects duplicate stacked target mountpoints and refuses alias-only proof
- `operation.status` resolves claimed job runs to their real status and progress without changing the durable journal's meaning of a successful *launch*

## Fail-closed and qualification limits
- Android builds with unsupported or restricted `dumpsys connectivity` layouts correctly yield unknown metering; do not treat the presence of Wi-Fi as evidence of `NOT_METERED`
- Network age cannot be attested across daemon restart from this source-only approach, and may reset conservatively
- VFS advice never mutates selected profiles or mounts
- Doctor presence checks do not qualify real cloud availability, ordinary-app namespace visibility, or physical-device lifecycle
- Progress is polled from the durable job-run store; this is not an independent event stream or completion attestation
- Static runtime only; dynamic runtime and migration support intentionally excluded
- All gates remain blocked pending independent trusted and device evidence. No final seal is issued.

## Devtool acceptance
The overlay's `validation.script` runs the affected package tests at `umask 022/077`, all Go tests, supported-host race tests, `go vet`, Android/arm64 compilation, previous WebUI/provider contracts, and the blocked-release audit. No external post-apply validation is required.
