# R1 — Consolidated BKX Android live socket acceptance (candidate)

Source-bound to Skybind `5877fba370898945b5a2b8ccc3dc532d7495ac8d`.
Independent BKX instrumentation source at `8886dc044976a3e5217190a4b85049cfcb23619f`.

## Scope

Adds an explicitly operator-invoked `acceptance-bkx REMOTE [PATH]` command to the existing interactive Skybind gateway. The command starts exactly one fixed AndroidJUnit instrumentation class using `/system/bin/am instrument`, accepts exactly one temporary Android abstract Unix coordination socket, checks `SO_PEERCRED` UID/GID/PID against the root-owned BKX pin, independently reverifies the process with the existing PackageManager-backed verifier before each phase, and issues only root-policy-covered, one-operation, exact-process grants. The client cannot request arbitrary scopes or choose a process identity. The root operator chooses REMOTE and optionally a small directory PATH. Neither tokens nor raw rclone output are written or printed. The control socket and issued grants are closed/revoked at completion. The ordinary production daemon and client ABI remain unchanged.

The test uses **real Android BKX process** -> authenticated handoff socket -> authenticated broker socket, not an in-process fake or root CLI substituted for the app. Twelve fixed, sequential cases:

- No token -> `not_authorized`.
- Five typed positive backend calls `system.capabilities`, `rclone.version`, `rclone.listremotes`, `rclone.lsjson`, `rclone.size`; assert safe response schemas, no raw metadata retained.
- With a genuine scoped grant, wrong operation, wrong remote and traversal path -> `not_authorized`.
- A debug-only, nonexported BKX service in an isolated second Android process receives the in-memory token via same-app Binder and attempts a real broker socket; the replay must return `not_authorized`, while the original approved process must still successfully use that token. Connection failures alone never count as successful denial. Debug-only component is absent from release APKs.
- After a genuine token is issued/delivered, root operator coordination calls `RevokeIssued` **before** the app sends the read; read -> `not_authorized`.
- With a genuinely delivered two-second grant, app waits past expiry; read -> `not_authorized`.
- Root gateway verifies actual same-process kernel identity repeatedly and requires a successful Android instrumentation terminal result. This does **not** cover another arbitrary malicious Android app UID or future signing-lineage changes; the prior chrootctl grant-store wrong-peer receipt stays separate evidence.

Each successful case also requires server handoff diagnostics `delivered==1, rejections==0` and a synchronous case assertion from the instrumented BKX process. Any timeout or failure BLOCKS, no optimistic PASS. The fully passing run sets `BKXNegativeSocketQualified=true` **only for the described socket scope**. It does not set external-provider or release qualification. A new root-only JSON schema `skybind-r1-bkx-device-acceptance-v1` is written under `/data/adb/skybind/r1-bkx-acceptance`, separately from chrootctl nine-case receipts. Permissions root:root / 0700 directory / 0600 file, fail-closed symlink checks. No older evidence is rewritten.

## Signing and installer constraints

BKX workflow `bkx-r1-device-acceptance-apks.yml` builds only ephemeral unqualified debug app + test candidate, with identical CI cert and SHA256/provenance manifest. It does **not** guarantee a match to the operator's installed BKX permanent signer. If installed BKX cert differs, do not uninstall/clear data, never force-install the test APK. Build/sign the Android test APK using an independently authorized matching signer or test on a separately authorized disposable installation. A missing compatible instrumentation package blocks this test. Running the new gateway also requires the separately hosted Skybind binary built from this source. `r1_collect_bkx_evidence.py` reconciles new BKX with immutable prior nine-case/device receipts, marking missing coverage honestly.

## Validation and status

Local Go focused tests, Go race tests and Android ARM64 gateway cross-build. No Android SDK environment available in the artifact authoring container: BKX Kotlin compilation and actual on-device execution must be verified by hosted CI and the operator. CURRENT STATE: SOURCE CANDIDATE; DEVICE NOT YET RUN. No broader release, external-provider or M2/M3 qualification claimed.

## Improvement ledger

- **Gap:** operator-reported BKX 5/5 UI positive runs lacked machine-readable independent Android-process negative socket evidence.
- **Risk:** previous root-only chrootctl store negatives could not legitimately qualify BKX app-process revocation, expiration, scope isolation.
- **Change:** one operator-owned BKX Android instrumentation campaign with real socket client; exact per-case results; zero token logging; separate root-private receipt.
- **Affected:** `Mikeyphw/skybind`, `Mikeyphw/bkx`; no chroot-ctl module changes.
- **Status:** IMPLEMENTED / LOCAL GO VALIDATED / HOSTED AND DEVICE PENDING. Signing-provenance and cross-UID/distinct-signer replay remain distinct qualification obligations.
