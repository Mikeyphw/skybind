# Skybind Phase A2 — WebUI operation progress (source-only)

Phase A2 presents the Phase A1 `operation.events` allowlisted extension in **Jobs** and **Activity**. It uses the existing typed authenticated bridge for both embedded KernelSU and standalone WebUI. There is no new port, unrestricted rclone RC proxy, change to the frozen 57-operation catalog, or modification of FUSE/offline/writeback code.

## Behavior

- On Jobs/Activity views only, polls `operation.events` using `{cursor,limit:64,wait_ms:0}` and maintains an in-memory cursor. Limits to one request loop per visible view generation. Leaving a view or hiding the WebUI stops new polls; a late response is ignored. On return it replays from the last cursor, while a new page session reconstructs recent retained events from cursor 0.
- Replays pages until caught up, showing the most recent run state per operation ID. Client memory is capped at 96 sanitized events. Backend spool retention remains 512 events.
- Shows transferred bytes, current speed, and ETA if known. No percent bar or total estimate is invented when unknown. An indeterminate animated strip respects reduced-motion preference.
- Detects server-reported gap, cursor reset and degraded spool state. An authoritative `jobs.status` check precedes safe cancellation controls. Activity is reloaded after a gap; Jobs periodically reload their authoritative status.
- Cancels using **actual 32-hex job run IDs** via existing `operation.cancel` with confirmation; requests are guarded by the latest authoritative `jobs.status` state (`RUNNING`). A cancellation request does not claim the job has finished. Backend owns the run and enforces the final cancellation.
- When event polling is unavailable, the UI shows a nonblocking progress-feed status; existing Jobs and Activity views remain operational. Event errors do not affect mount behavior, offline edits or provider jobs.
- No credential, remote path, stderr, secret, or filename is read from the new event stream. All inserted text uses `textContent` rather than HTML injection. No localStorage is used.

## Qualification

Source tests: `node tests/webui/test_phase_a2_progress.mjs`, all existing WebUI tests, Python HTML parity/frozen catalog, Go regression/vet, and Android arm64 cross-build. Source tests cannot prove KernelSU WebView scheduling, transport reliability, or in-device cancellation.

On-device acceptance after a deliberate build: run a long **copy** job from a configured remote without mounting; open Jobs, observe rising bytes/speed/ETA, switch to Activity and back; background and reopen WebUI; verify catch-up without duplicate activity and without losing the job; cancel another deliberately disposable copy and verify a terminal cancelled state. Exercise a >512 event history for gap behavior and offline write safety. Do **not** use destructive sync as the test job and do not cancel live queued writeback work.

The Phase A2 panel only renders numeric progress, not reliable total percentage or file count. That requires future additions to the backend event fields and tests.
