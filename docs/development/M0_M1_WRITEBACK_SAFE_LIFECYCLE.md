# Skybind M0 + M1 — trusted VFS writeback and safe mount lifecycle

## Operational behavior

- The existing authenticated per-mount `rc.metrics` response now contains a sanitized `writeback` snapshot from rclone `vfs/stats` (`diskCache.uploadsQueued`, `uploadsInProgress`, `erroredFiles` and root `inUse`). No directory paths, filenames, credentials or raw RC output are exposed.
- State is `idle`, `busy`, `errored`, or `unknown`. Missing, malformed or unsupported counters are **unknown**, never zero. The WebUI checks this state before offering Stop or Restart.
- Root daemon rechecks with private authenticated RC credentials after verifying the owned FUSE PID/start ticks/mountinfo. A busy queue waits at most 20 seconds (1-second checks) before refusing to unmount. Errors, unknown status, timeouts and cancellation fail closed; desired state remains unchanged and the cache is preserved.
- This includes the shared stop path used for mount configuration changes; an unsafe config change can fail rather than detach a busy mount.
- The original process identity, mount ID, no-foreign-unmount, bounded RC transport, and provider-binary guarantees remain unchanged.
- Stop/Restart attempts cancelled by backend context do not detach; **current WebUI Cancel cancels the confirmation**, not an in-flight operation. Active operations have a 20-second bound; an interruptible post-confirmation cancel button remains future work.
- Stopped-cache cleanup is **not** changed in this phase. Stopped caches can retain dirty uploads and must not be assumed safe to evict. A later M3 cache change must add durable dirty-cache classification.

## Test and rollout

Run `go test -count=1 ./...`, `go vet ./...` and `node --check module/webroot/app.js` before building a new personal candidate. Test on device with an idle mount, a file upload still in progress, and unavailable RC telemetry. For safety, a startup/provider combination without the expected writeback counters will block Stop/Restart rather than force unmount. Confirm normal idle Stop/Restart on your installed provider **before** relying on this candidate daily.

The module build remains a personal candidate; there is no automatic install, independent attestation, or CFS1 promotion. Install only after validating the candidate locally and retain the previously working KernelSU module for rollback.

## Acceptance against roadmap

- M0 — read-only authenticated counters, explicit unknown/error states, redacted JSON: implemented, source-tested; real-device compatibility pending.
- M1 — guard before Stop/Restart, bounded drain, timeout, preserve cache and mount state on refusal: implemented, source-tested; real-device upload-in-progress test pending.
- In-flight UI cancellation and durable tracking of offline dirty cache across daemon restarts: **not yet implemented**, tracked as follow-on acceptance requirements. Never claim those properties from the current tests.
