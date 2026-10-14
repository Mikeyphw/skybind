# Skybind continuation roadmap — A1–B3 device acceptance and remaining work

**Status: source-applied A1–B3 per user; not yet installed-and-device-qualified as a combined release.** The user is collecting independent auto-start diagnostics. This roadmap is *not* evidence that any pending item is complete. Updated 2026-10-14.

## In-scope phase history

- A1: durable, bounded operation-event store, cursor replay, job lifecycle and CLI event follower; frozen original API catalog unchanged.
- A2: Jobs/Activity live progress WebUI, cursor reconnect and authoritative status-based cancellation; correct `jobs.status.runs` integration.
- A3: rclone rich transfer totals, percentages, files transferred/checked, errors and throughput from events; explicit numerical transfer retries only when actually supplied.
- B1: configured mountless remote list/stat; proof-backed remote copy/check, skip existing and reject dangerous sync/move.
- B2: remote selection and proof confirmation in WebUI; progress view in Remotes/Jobs/Activity.
- B3: bounded exchange-folder upload/download, proof-backed mkdir, single-file same-remote move/rename; remote root, folder moves, cross-remote moves, deletion and destructive sync disabled.

## Test and evidence sequence (before release)

1. Confirm exact post-B3 source and Devtool wrapper resolution, full Go/vet/WebUI source checks, Android arm64 build.
2. Build personal KernelSU module from this source using `./devtoolw personal-release`; verify candidate receipts/provenance, user installs deliberately and reboots. **The source overlays alone do not update the installed module.**
3. `./devtoolw api-device-readonly` and opt-in `./devtoolw api-device-disposable`. Preserve Devtool run IDs, qualified time window, SHA-256 of installed ELF, device JSON and per-test PASS/FAIL/BLOCKED. Upload result ZIP.
4. Physically exercise WebUI as KernelSU WebView: `ksu.exec` invocation, navigation, proof changes, transfer panels, progress, reconnect, cancellation. Independent on-device proof is still needed.
5. Join device results with earlier M0–M8 HYBRID suite, ordinary Android app UID FUSE probes, startup captures, offline journal and data-integrity testing. Report historical FAILs/NOT_RUNs honestly.
6. Reconcile source-build artifact to installed binary and original CFS1/G01–G08 gates; only issue a release after independent completion, not simply after a personal candidate build.

## Priority repairs that remain after the API detour

### Startup reliability

- Repeated `start_error_other` failures on mount autostart; CE-storage gate was added but the Oct 14 14:38Z diagnostic still recorded five failures, no `RECONCILE_STORAGE_DEFERRED`, mount `STOPPED`, and delayed cooldown. Root cause **not established**.
- CE property gate checks literal `false`/`0`; early-boot empty/unset property is a plausible bypass, requires actual property sample and typed fix, not speculative retry increase.
- Root-shell early recorder found mountpoint levels 4/5 unavailable until ~276 seconds of uptime and CE unavailable; confirm daemon mount namespace/timing, boot IDs, `getprop` read behavior and precise `Start()` failure categories rather than misclassifying `start_error_other`.
- Preserve five bounded initial attempts and two delayed recovery probes, retry persistence, explicit Stop, FUSE mount identity, cache/writeback correctness. Qualify over several independent boots including late unlock and network off/on.
- Root namespace FUSE visibility in early recorder remained false even after CE availability; this **may be namespace mismatch**, not definitive mount failure. Compare actual mount namespaces and ordinary app UID access.

### WebUI resilience

- Historical `Embedded backend exited with status -1` in KernelSU WebUI. Direct `skybind webui bridge --capabilities` returned zero; source-level stale Home error banner was patched and reported working. This does *not* prove every transient `ksu.exec` failure is recovered.
- Add bounded retries with jitter, typed transport failures, retryability, abort on hidden WebView, no duplicate operations after retry, stale response suppression, and recovery without forcing page reopen. Reconcile Root manager WebView lifecycle across devices.
- Test history replay and progress view across hide/show, restart, short jobs and interrupted transfers. UI accessibility and narrow mobile layouts, webview crash/failure injection, offline state.

### Offline/writeback and data safety

- Previously queued offline edit recorded `QUEUED` with `UNKNOWN` revision; preserve it, never auto-flush or overwrite while tests run. Establish conflict semantics and revision identity before reconciliation.
- Automated interrupted upload/writeback recovery, journal replay, hash-based remote consistency, duplicate/conflict and partial-file scenarios; ensure no unsafe retries or stale mount assumptions.
- Qualify behavior when remote changes during preview, copy, download or same-remote move; B3 move can race external destination creation even with `--ignore-existing`. Guarantee no data loss or explicitly report unresolved race.
- B3 uses folder-only exchange area `Download/Skybind-Transfers`; expand later to user-approved SAF file picker with Android URI grants and app UID testing, without exposing arbitrary root paths.
- Improve storage quota checking, cache dirty-state protections, symlink traversal defenses, cancellation/resume boundaries. Distinguish no-overwrite skip from verified matching content.

### API roadmap after A/B

- B4: per-file upload/download with SAF, safe metadata and file previews, selective transfers and checksums, paginated large remote listings; preserve privacy filtering.
- B5: schedule and policy engine (Phase C): recurring sync/check, connectivity/charging/storage constraints, durable checkpoints, notifications, opt-in job templates, constrained concurrency/quotas.
- B6: guarded sync/delete only after robust preview/diff, device acceptance, recycle/undo plan, conflict model and explicit permission separation. Keep disabled until then.
- Phase D: documented versioned CLI/SDKs, scoped per-client auth, remote API optional transport only with explicit opt-in; never expose unrestricted rclone RC or unauthenticated network port.
- Progress improvements: stock rclone numeric per-file retry count generally unavailable; expose truthful unknown state, file-level stats only when safe, throughput history bounded, throttling/network wait events, SSE only when a secure external listener is justified; existing callback bridge should retain cursor polling.
- Operation storage has a bounded 512-event history; add pressure/rotation policies, gap handling, test resumability and interruption semantics, event privacy and correct progress ratios across transfers/checks.

### Release qualification and automation

- Source/tests do not replace real Android tests. Preserve G01–G08/CFS1 evidence, vendor runtime provenance, static engine/FUSE checks, KernelSU installation and app UID namespace probes, original M0–M8 cases, WebUI parity, source-bound Devtool transaction traces.
- Consolidate device evidence ZIPs with exact build/boot identity and negative case failures; do not erase historical errors. Full test matrix covers read-only, destructive proof negative tests, cloud provider differences, bad network, repeated reboot, offline/writeback and fallback.
- Qualified signed release gating remains distinct from personal builds. Devtool may mark wrapper collector invocation success while tests are `BLOCKED` and no independent attestation exists.

## Handoff package — intentionally deferred

Only **after** the new on-device tests and remaining acceptance obligations are truly proven, create the requested full handoff ZIP for a new chat. Include up-to-date source snapshot, applied overlays A1–B3, this roadmap, current Devtool wrapper contracts, test kit, device result ZIPs and checksums, startup diagnoses, outstanding gate ledger, exact command examples, and explicit unfinished/blocked findings. Don't claim a completed handoff yet.
