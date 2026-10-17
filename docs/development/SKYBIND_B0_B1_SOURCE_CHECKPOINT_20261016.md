# Skybind B0+B1 — First source implementation checkpoint

2026-10-16. Baseline Skybind Git SHA: `7a1c8168fbc82603ce999ecc21d9ba791ce10779`. Devtool archive was `devtool-20261015-183913-544711.tar.gz`. This is a **source implementation**, not an Android build, broker acceptance or release seal.

## Applied functionality

1. Existing BKX R0 read-only parser/source contract imported from the approved handoff, 8 exact source file digests verified offline.
2. New chrootctl R0 command/flag matrix: `version`, `lsjson`, `cat`, `rcat`, `moveto --immutable`, `deletefile`, 6 reference SHA-256s; archived `.go.fixture` bytes avoid treating alien module code as Skybind Go packages.
3. New `internal/brokergrant` deny-by-default R1 policy core with kernel-verified identity input contract, per-remote/prefix scopes, query-only operations, short-lived random tokens, SHA-256 token storage, expiry and revocation. **Not connected to the cross-UID transport; no privileged RPC route enabled.**
4. Source-bound Devtool targets for native Go, BKX, chrootctl, R1 grant policy, Android source-build policy, plus `skybind_release#r0-compat` and `#r1-source` real DAGs. Device jobs have `device-exclusive` metadata and global phone reservation; receipt-producing jobs no longer mislabeled repository-read-only.
5. Compose native app scaffold with Home, Browser, Jobs, Activity and Settings. Jobs is an operational queue while Activity is a read-only chronological journal. No root/IPC/remote operations enabled yet. Separate Android instrumentation test source.
6. GitHub Actions-only debug app and test APK build workflow with SHA-256 manifest, certificate fingerprints, exact source SHA, GitHub run ID/attempt/ref/workflow, explicit no-device/no-release flags. Independent authenticated GitHub artifact correlation remains next work.
7. Previously reachable legacy `skybind_app_probe` local Android Gradle builder disabled: old build and install wrapper workflows now return `BLOCKED_BY_POLICY`. Original Q10 test contract archived; current tests confirm the retirement. No Android builds were performed here.

## Executed evidence

- Offline Python source/manifest tests: **19 tests PASS**.
- Updated legacy Q10 tests: **8 tests PASS**, including the retired local compiler path.
- `go test ./...`: PASS over 33 packages (2 no-test), including new broker policy and existing daemon/control tests.
- Uploaded-source Devtool `plan` on `skybind_release#r0-compat` and `#r1-source`: PASS; R1 planner resolves four nodes.
- Uploaded-source Devtool **`invoke r1-source --target skybind_release`**: PASS, four stages, 270 Go tests PASS, 31 Go packages passed + 2 no-test, 0 warnings/errors, approximately 9.52 seconds. An earlier run failed because imported consumer `.go` files were within Skybind's package discovery. Their storage suffix was corrected; the next complete run passed.
- Android GitHub workflow YAML parsed; Android source-only local build prohibition check passed. **No hosted APK build, device installation, R1 transport acceptance or publication occurred.**

## Important next gates

- Push resulting changes to branch, trigger `.github/workflows/skybind-android-apks.yml` on GitHub Actions, inspect actual Gradle/Kotlin compilation; fix as needed. Nothing has been remotely built yet.
- Devtool Actions dispatch/resume should authenticate completed run SHA/attempt/workflow/job/artifact IDs before remote output adoption; local byte verifier by itself DOES NOT authenticate GitHub run.
- Implement Android process/installer receipt verifier and source-verified cross-UID broker transport (current root Unix socket stays UID-locked). Identity must use real BKX package signature/process and sealed chrootctl module executable, not self-reported process keys. No arbitrary privileged command bridge.
- Implement R2 scoped remote metadata, then real broker tests from BKX and chrootctl processes; satisfy R1 read-only grant and revocation on phone.
- Cloud-only rule applies to all future Skybind APKs; do not revive legacy `skybind_app_probe` AndroidGradleRunner locally.
- Full R2–R6, native UI, CFS1, device reboot/recovery, WebUI retirement decision, and final release qualification remain incomplete.

**Toolchain review:** AGP 8.9.2 requires Gradle 8.11.1; Kotlin Gradle plugin 2.2.21 is within the documented support matrix for AGP 8.9 and Gradle 8.11.1. The earlier untested 2.0.21 pin was corrected before delivery. This is documentation verification, not a successful hosted APK build.
