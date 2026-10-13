# Skybind M0–M8 — Source delivery audit

**Scope:** October 13 supplied Skybind source snapshot (post-M8). **Personal-project standard**: meaningful regression coverage and real-phone testing, not third-party release certification.

**Source result:** full Go suite and `go vet` pass before/after the targeted fix. Device behavior is NOT confirmed by source tests.

## Coverage ledger

| Milestone | Promise | Source status | Evidence |
|---|---|---|---|
| M0 | Authenticated VFS upload telemetry | **IMPLEMENTED** | `internal/mounts/writeback/writeback.go` |
| M0 | Stop/Restart display unknown/errored state | **IMPLEMENTED** | `module/webroot/app.js` |
| M1 | Writeback-aware Stop/Restart bounded 20s | **IMPLEMENTED** | `internal/mounts/lifecycle/engine.go` |
| M1 | Cancellation after WebUI confirmation during wait | **NOT IMPLEMENTED** | `docs/development/M0_M1_WRITEBACK_SAFE_LIFECYCLE.md` |
| M1 | Durable proof of clean stopped VFS cache | **NOT IMPLEMENTED** | `internal/mounts/cache/cache.go` |
| M2 | Per-mount performance, cache, transfer, upload status | **IMPLEMENTED** | `internal/rc/performance_m02.go` |
| M2 | Bounded history, hidden-page pause and PID change reset | **IMPLEMENTED** | `module/webroot/app.js` |
| M3 | Existing and new performance profiles including documents/read-only/offline-ready | **IMPLEMENTED** | `internal/mounts/policy/policy.go` |
| M3 | Read-only enforced in actual rclone command | **IMPLEMENTED** | `internal/mounts/lifecycle/engine.go` |
| M3 | Native min cache free-space, cache pressure advisory | **IMPLEMENTED** | `internal/mounts/policy/policy.go` |
| M3 | Stopped cache will not delete unverified files | **IMPLEMENTED** | `internal/mounts/cache/cache.go` |
| M4 | Network change notifications and recovery timing | **IMPLEMENTED** | `internal/mounts/networkwatch/watch_linux.go` |
| M4 | Respect policy-deferred and real-failure backoff | **IMPLEMENTED** | `internal/mounts/supervisor/supervisor.go` |
| M5 | Individual and directory pinning verified full files | **IMPLEMENTED** | `internal/offline/offline.go` |
| M5 | Quota, manifests, offline verification and export | **IMPLEMENTED** | `internal/offline/offline.go` |
| M5 | WebUI pin/export/unpin/quota and background tasks | **IMPLEMENTED** | `internal/control/offline_extension_m05ui.go` |
| M5C | Verified separate offline views | **IMPLEMENTED** | `internal/offline/view_m05c.go` |
| M5 | Transparent same-path fallback to pinned files within rclone FUSE | **NOT IMPLEMENTED** | `docs/development/M5C_VERIFIED_OFFLINE_VIEWS.md` |
| M5 | Refuse public export for stale remote identity | **HOTFIXED** | `internal/offline/offline.go` |
| M5 | Rehash bytes actually exported | **HOTFIXED** | `internal/offline/offline.go` |
| M6 | Editable offline draft and persistent staged queue | **IMPLEMENTED** | `internal/offline/writes_m06.go` |
| M6 | Remote conflict check and explicit separate-copy upload | **IMPLEMENTED** | `internal/offline/writes_m06.go` |
| M6B | Opt-in reconnect review and uncertain-upload inspection | **IMPLEMENTED** | `internal/offline/reconcile_m06b.go` |
| M6 | Automatic reconnect upload and in-place reconciliation | **NOT IMPLEMENTED** | `docs/development/M6B_RECONNECT_REVIEW.md` |
| M7 | Checksummed portable backup excluding credentials and file content | **IMPLEMENTED** | `internal/backup/backup.go` |
| M7 | Preview / proof-bound disabled-mount restore | **IMPLEMENTED** | `internal/daemon/backup_m07.go` |
| M7 | Encrypted credential and offline-file migration | **NOT IMPLEMENTED** | `docs/development/M7_PERSONAL_BACKUP_RESTORE.md` |
| M8 | Consolidated mount controls and lower idle WebUI polling | **IMPLEMENTED** | `module/webroot/app.js` |
| M8 | Prevent stale metrics across mount restart | **IMPLEMENTED** | `module/webroot/app.js` |
| M8 | Personal Release integrated UI/regression checks | **IMPLEMENTED** | `scripts/dev/integration/local_build.py` |
| M8 | Physical device battery/performance benchmarks | **DEVICE PENDING** | `docs/development/M8_PERSONAL_INTEGRATION.md` |

## Actual missing or limited work

**M1:** The button can cancel the *confirmation* but not an in-flight 20-second backend drain. A persistent, independently proven clean-cache manifest is not implemented. Consequently nonempty stopped caches remain protected from destructive cleanup. Do **not** bypass this with manual `rm -rf`.

**M5:** Verified pins and public offline views work at *separate* paths. Transparent same-path offline FUSE reads are not implemented because rclone owns FUSE. Claiming success through `/storage/.../Skybind-Offline-Views/` is not proof that the original mounted path works offline.

**M6:** Reconnect auto-review is opt-in and metadata-only; there is no automatic upload, original-file overwrite, merge or conflict resolution. These are safety trade-offs, not passing tests of automatic sync.

**M7:** Portable config backups intentionally exclude rclone credentials, private offline object bytes and queued journals. Encrypted credential migration was deferred.

**M8:** Actual idle battery impact, mount time, cache/storage behavior and ordinary-app usage on Android remain unmeasured.

## Concrete audit hotfix

Previously, exporting one stale pinned file to Android Downloads verified local SHA-256 but did **not** ensure that the current mount name still referred to the remote it was originally pinned from. This could unexpectedly expose an old remote’s data after a mount was repointed.

`internal/offline/offline.go` now compares the configured mount remote identity with the pin before creating public output, and computes SHA-256 over the bytes actually exported. Failure deletes an incomplete public output. A regression test covers changed and removed mounts. Offline status and whole-view publication already checked source identity; this closes the single-file gap.

## Suggested next development, after device tests

1. **M1C:** backend operation token + user-invoked cancellation during a pending writeback wait. Do not force-kill rclone.
2. **M3C:** persistent clean-cache accounting, only if backed by robust crash-safe rclone evidence; until then refuse stopped-cache eviction.
3. **M5D (research, not casual hotfix):** evaluate provider-native read fallback in a disposable mount without hiding dirty VFS writes.
4. **M6C (optional):** explicit per-file reconciling state machine; no automatic overwrite unless backend offers atomic revision compare-and-swap.
5. **M7C (optional):** authenticated encryption for credentials and private data with user-held key; never store it in the evidence bundle.

## Where to run practical tests

Use `docs/development/M0_M8_REAL_DEVICE_TEST_PLAN.md` and `scripts/dev/integration/m0_m8_device_tests.py`. The JSON case catalog has 34 actual device scenarios; missing capabilities have a dedicated `BLOCKED` case so results cannot be accidentally overstated.
