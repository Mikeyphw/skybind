# Skybind R1 — real `rclone size --json` compatibility

**Trigger:** On the installed Android BKX client, all other tested R1 metadata operations worked; only Size showed unavailable/denied. The same process-bound IPC gate was previously proven with BKX and chroot-ctl.

**Cause:** Strict Skybind `Metadata.Read` decoder allowed only `count` and `bytes`. Rclone's canonical `cmd/size/size.go` JSON also writes `sizeless` and `fs`; `DisallowUnknownFields` therefore denied *valid* production Size responses. Tests had used a synthetic minimal two-field fixture.

**Change:** Accept the four upstream keys; validate required counts and bounded numeric values; verify `fs` exactly matches the validated operator-approved request target; omit `fs` when returning read-only JSON, optionally include `sizeless` > 0 to indicate objects without known sizes. Preserve default-deny behavior for all unknown fields and malformed payloads. No APK/module changes, no root policy changes, no automatic grants, no SELinux changes, no new operations.

**Evidence still needed:** New exact-source hosted Android arm64 gateway; device live `Skybind Size` against a small folder, receipt with `delivered=1` and valid `count`/`bytes`; subsequent denial, expiration and revocation tests. Source tests are NOT remote-device or release qualification.
