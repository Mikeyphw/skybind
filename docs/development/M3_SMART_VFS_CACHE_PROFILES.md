# Skybind M3 — Smart VFS cache & mount profiles

**Track:** Personal Release, after M0+M1+M2. This milestone does **not** issue a CFS1 release seal.

## Source changes

- Added `documents`, `read-only` and `offline-ready` VFS profiles while retaining the legacy `offline`, `streaming`, `balanced`, `minimal` and `custom` profiles.
- `read-only` is enforced at the actual rclone invocation (`--read-only`), even when an older config field has `read_only=false`.
- A VFS-profile change now requires a safe managed mount restart in the guarded registry plan; resource-policy-only changes do not.
- Profiles advertise descriptions and resolved read-cache options to the mount wizard; `custom` continues to allow explicit overrides. The wizard shows only cache-related flag semantics (not secrets, remote endpoints, the cache directory or the entire command line).
- An explicitly configured `min_cache_free_space` now also goes to rclone's native `--vfs-cache-min-free-space` limit, in addition to the existing policy startup check. rclone's cache size/age limits remain soft eviction controls, **not hard resource quotas**.
- M2's per-mount Performance section adds cache-pressure advice (high/normal/unknown) based only on authenticated measured VFS cache usage and configured thresholds. `unknown` never becomes `0`.

## Writeback and data preservation

**Important fix:** The old `AutoPruneStopped` deleted the oldest files from a stopped mount's cache without knowing whether an interrupted VFS upload was waiting for a later restart. Stopped **does not mean clean**. A stopped mount has no authenticated live RC to prove durable upload completion.

M3 now conservatively prevents deleting any nonempty, unverified stopped cache through manual clear/prune/forget or automatic pruning. Even a valid preview token cannot override this check; no new operation can delete such files. Empty cache operations still work. The supervisor does not repeatedly scan an offline cache. Automatic pressure management is delegated to rclone **while it is running**, when it knows its dirty-file state.

This temporarily reduces manual cache cleanup functionality, intentionally. Safe selective cleanup of a stopped cache needs a durable, verified clean-file manifest and crash-recovery semantics, which are not currently implemented. Do **not** manually remove `/data/adb/skybind/cache` as a workaround: pending writes may still be there.

## Testing and compatibility

- Go full suite and `go vet`; new backend tests for profile registry, restart effects, real read-only flags, min-free-space, unknown cache pressure and stopped dirty-cache preservation.
- Node model tests for pressure and UI option derivation; earlier M2 WebUI model/parity tests.
- Operation catalog remains the original 57 operations; no generic RC proxy, no new privilege bridge, no FUSE implementation change, no new daemon.
- The baseline is **the exact M2 source hash set** reconstructed from the previously delivered verified M2 overlay. The Devtool preflight rejects mismatch, pre-existing M3 paths, and dirty Git worktrees.

## Android device smoke test (not executed here)

1. Preserve a copy of the last working Personal Release ZIP. Apply overlay, build, install, open Mounts → Edit → Performance.
2. Confirm `documents`, `read-only`, and `offline-ready` cards with detailed options; check `offline-ready` clearly states it does **not** pin full files for airplane mode.
3. Apply `read-only` on a disposable test remote and verify a normal Android app cannot write; restore previous profile via the guarded preview/restart path. Do not test against irreplaceable files.
4. Expand Performance during moderate remote use; cache pressure should update only when measurements are valid, without confusing a soft cache target with hard enforcement.
5. Stop with a queued upload (on a disposable file): M1 should wait or block; restart must recover the pending write. Automatic supervisor pruning and manual stopped-cache clear/prune/forget must not delete unverified files.
6. Check ordinary-app file access, restart recovery, narrow-screen editor layout, and both provider variants if available.

**Not yet complete:** verified clean-file selective pruning, Android WebView interaction check, comparative cache/seek benchmarks, and sustained testing of both provider binaries. These remain explicit M3 follow-up obligations, not silent passes.
