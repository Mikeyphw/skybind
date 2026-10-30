# API-05 R1 — explicit safe recovery of obsolete mount ownership

## On-device cause

`mount.list` returned `safegdrive`, but `mount.status` and `mount.health` returned `operation_failed` after module update. The previous FUSE owner PID 3634 was reused by `/vendor/bin/mtk_agpsd`, with different process start ticks and executable path. The daemon observed no mount at `/storage/emulated/0/Rclone/SafeGDrive`; an independent `/proc/*/mountinfo` sweep returned no path matches, although missing permissions can make a shell sweep inconclusive.

## Scope

- New root-daemon operations: `mount.stale.preview` (preview) and `mount.stale.recover` (run). Both are outside the frozen app/WebUI catalog and have only a fixed root-CLI interface.
- A short-lived one-use proof binds registry revision, the exact saved ownership record and the configured mount. Replay and wrong revision reject.
- Before issuing a proof and again before applying, revalidate: owner record canonical and root-private, recorded process identity **no longer matches** (or process vanished), no mount exists at configured destination in daemon namespace, and the process-namespace mount inventory is fully readable and contains no mount at the path. Missing privileges or uncertain scan data fail closed.
- Archive the stale record inside `/data/adb/skybind/desired/` as root-owned `0600`, persist `desired=false` (prevents supervisor autostart), then remove the old primary record only after another proof-independent recheck. The mount config, cache and remote credentials remain unchanged. **No kill, SIGTERM, unmount, global reconcile, implicit restart or boot modification.**
- Existing `Stop`, `Start`, ownership guards, and API-04 endpoints are unchanged.

## Operator flow (AFTER installing this new module)

1. `su -c '/data/adb/modules/skybind/system/bin/skybind mount stale-preview safegdrive'` to obtain the one-use `result.proof`. Do not proceed on `ok:false`.
2. With explicit approval, send `{"name":"safegdrive","proof":"<from preview>","operator_approve":true}` as private stdin to `su -c '/data/adb/modules/skybind/system/bin/skybind mount stale-recover --stdin'`. Do not publish the proof.
3. Confirm `mount status safegdrive` now reads `STOPPED` and persisted desired is false. An explicit, separately approved start is required.
4. If `/proc` namespace inspection is denied, the operation **must refuse**; collect its structured failure evidence, do not delete the record manually.

## Qualification and residual risk

Host suite passes on reconstructed source; full `go test`, `go vet`, and an overlay Devtool transaction on the exact remote HEAD are mandatory. App / KernelSU installation and actual namespace completeness remain **device-pending**. No user-space scan can atomically freeze all external Android namespace creation; this operation nevertheless never targets an external process or detaches a mount.
