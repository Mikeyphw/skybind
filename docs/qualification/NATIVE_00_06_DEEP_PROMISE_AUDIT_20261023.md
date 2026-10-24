# Skybind Native NATIVE-00–06: source-to-behavior audit and qualification boundary

**Audited snapshot:** uploaded `skybind-20261023-211330-315069.tar.gz`; clean `HEAD 02bf99fb47a5fa7c8509aa672f0438142123a621`; baseline tree `278c3a950c31763b3a3a1fc399293689c741563a`.

**Scope:** compare the original `SKYBIND-NATIVE-PERSONAL-R1` roadmap, every NATIVE-02–06 promise document, actual Compose/activity/bridge/daemon implementations, source gates, CI packaging, and acceptance runner. Audit claims refer to the *hotfixed postimage* when marked FIXED HERE. Prior approved Skybind PERSONAL module is a historical different-source artifact. No APK/device run was executed during this source audit.

**Method:** trace observable user action to state owner and daemon contract, test both positive and negative policies, inspect release receipt authority and supporting evidence. Mere file presence or constant-checking source gate does not count as device acceptance.

## Every milestone: promise-to-evidence matrix

| ID | Original obligation | Implementation / behavior verified | Source finding | External evidence |
|---|---|---|---|---|
| 00-01 | Android changes invalidate historical APK evidence | `scripts/dev/qualification/personal_policy.py` Android native source classification; negative `tests/qualification/test_native_android_evidence_compat.py` | DELIVERED | Future APK must be fresh |
| 00-02 | Preserve unaffected provider evidence without falsifying source | personal policy distinguishes recorded b46d2d5 historical evidence and current APK lineage; source commit never rewritten | DELIVERED | Review policy receipts on new module release |
| 00-03 | Current source, signer, previous evidence recorded | Git `HEAD`/tree; NATIVE-05 manifest, Q16/Q17/R1/m2m3 historical receipts; no implied cross-qualification | DELIVERED within scopes | Installed APK+root manager still must be observed |
| 00-04 | Replace obsolete source gates, don't disable them | `native_personal_foundation_gate.py`, M1/M2/M3 source gates remain executable; auto-connect expectations updated | DELIVERED / FIXED HERE | GitHub compile pending |
| 01-01 | Themed header, status/nav safe insets, no overlapping R1 banner | `MainActivity.kt`, `SkybindApp.kt` Material header and `statusBarsPadding()` | FIXED HERE: explicit Android 15/16 status inset | API 35/36 screenshots pending |
| 01-02 | Launcher Skybind; SVG-derived adaptive, monochrome and notification icons | Android strings, mipmap adaptive, drawable, notification, splash and NATIVE-05 branding gates | DELIVERED | Mask and contrast visual inspection pending |
| 01-03 | Existing package/signing continuity, distinct personal channel | app ID `io.github.mikeyphw.skybind`; hosted persistent signer; personal build type/version, no uninstall fallback | DELIVERED | Signer + installed upgrade not yet observed |
| 01-04 | Automatic foreground root connect, bounded reconnect, stable denial | `SkybindSessionViewModel.onForeground`, session binder; explicit disconnect/opt-out; loss-only bounded retry | FIXED HERE: foreground return after authenticated background loss | Live allowed/denied root review pending |
| 01-05 | No implicit mount/job/background FGS start | `SkybindSessionViewModel`, `MainActivity`, BKX service and separate explicit action controls | DELIVERED | Live device observation pending |
| 01-06 | Five destinations and Activity under Jobs/More | `SkybindApp.kt`: Home, Mounts, Browser, Jobs, More; Activity routing | DELIVERED | Device navigation test pending |
| 01-07 | Truthful mount status/count/health and stale handling | `LiveReadSnapshotReader.kt`; read-only exact daemon `config.snapshot`, `mount.status` and health queries; unknown fail-closed | DELIVERED | 0/stopped/running/degraded on device pending |
| 01-08 | Browser retains folder, efficient lazy rows and human sizes | keyed `LazyColumn`, folder-specific scroll state and refresh logic | DELIVERED | 200 files / long names device test pending |
| 02-01 | Separately typed start/stop/restart/reconcile Binder methods | AIDL and `RootReadBridgeService.kt`, UI mount actions; no generic root RPC | DELIVERED | Actual Binder root device tests pending |
| 02-02 | One-use daemon start preview proof | root process holds daemon preview proof; client receives opaque bounded ticket | DELIVERED | Device proof-replay test pending |
| 02-03 | Stop/restart/reconcile guarded by identity, revision, state and single-use ticket | 60-second per-session ticket; fresh daemon preflight; daemon-owned operation | DELIVERED | Device FUSE/writeback cases pending |
| 02-04 | Explicit operator confirmation; no auto-writes | Mounts consent/checkbox, no launch/refresh mutation | DELIVERED | Device consent negative pending |
| 02-05 | Preserve difference in assurance between start and other actions | Stop/restart/reconcile **do not** have daemon-issued preview proofs; use root-service ticket + daemon preflight, documented without overclaim | DELIVERED with narrower security claim | Independent security assurance not claimed |
| 03-01 | Source, Destination, Behavior, Review four-step native wizard | `MountConfigEditor.kt`, typed draft UI and save-state | DELIVERED | End-to-end device rendering pending |
| 03-02 | Create, edit, delete with one-use daemon validate/preview/apply proof | dedicated AIDL + root process full candidate + daemon proof kept private | DELIVERED | Disposable device mutation pending |
| 03-03 | Remote, mountpoint, VFS/cache/network/battery/advanced policies | typed fields/validation and bounded registry transport | DELIVERED | Device field/path cases pending |
| 03-04 | Unrelated entries preserved, stale revision fail-closed | full snapshot, digest and revision proof; negative tests | DELIVERED | Concurrent edit device check pending |
| 03-05 | Structured field-level errors without credential leakage | bounded `FieldValidationError` → protocol fault → scoped field codes → native messages | DELIVERED | Runtime/UI propagation pending |
| 03-06 | Full native previous-known-good registry rollback | dedicated preview/apply rollback Binder, explicit whole-registry review | DELIVERED | Real rollback/recovery pending |
| 03-07 | Crash/busy/writeback safety; replay/foreign session denial | daemon transactional rollback and tests, server-side single-use identity checks | DELIVERED | Busy FUSE root test pending |
| 03-08 | Disposable instrumented create/edit/rollback/delete | `NativeMountConfigLiveTest.kt` tests existence/cleanup, but not yet executed | SOURCE TEST EXISTS | Execute on selected device |
| 04-01 | Home backend identity, FUSE/mount & OS-network truth | authenticated runtime status, mount health, OS network clearly labeled; no Binder=FUSE conflation | DELIVERED | Physical health test pending |
| 04-02 | Jobs speed/ETA/bytes, owned cancellation, receipts and replay gaps | `SkybindApp`, UI models, existing jobs permission boundary | DELIVERED | Real M3 CHECK/COPY/cancel pending |
| 04-03 | Activity human timestamps, severity, lazy bounds, technical expansion | native activity presentation/filter and lazy keyed rows | DELIVERED | Device high-volume event observation pending |
| 04-04 | BKX Off/Starting/Active/Failed + notification and background preference | service peer vs authorization separation; opt-in foreground service | DELIVERED | Notification/FGS device review pending |
| 04-05 | More diagnostics/privacy/build/signature provenance | About/build cert lookup, runtime/network/mount summaries | DELIVERED | Validate installed device display pending |
| 04-06 | >=48dp semantics, large fonts, offline/empty, orientation | Compose tests and layout/safety source | DELIVERED in source | API35/36 + 200% font screenshots pending |
| 05-01 | Hosted separate non-debuggable APK + AndroidTest | `.github/workflows/skybind-personal-apk.yml` present on GitHub main at `02bf99f`, workflow main-only signer | DELIVERED workflow | Latest changed-source workflow not executed |
| 05-02 | Increasing versionCode, package ID, stable signing identity | Gradle personal config, private CI keystore pin, no default debug signer | DELIVERED | Compiled aapt/apksigner and upgrade pending |
| 05-03 | APK signing/provenance, permissions, toolchain source receipt | `personal_apk.py` exact artifact metadata/pins, `personal_apk_device.py` signed fetch | DELIVERED | Real CI manifest/run pending |
| 05-04 | Non-destructive opt-in in-place upgrade & verified installed pair | installed APK/readback, signer/version checks, no uninstall or data clear | DELIVERED | Device install evidence pending |
| 05-05 | Monochrome themed launcher/splash/notification and privacy | drawable/mipmap + status notification resources | DELIVERED source | Device mask/contrast review pending |
| 06-01 | Exact fresh same-source GitHub/installed APK/test pair | run SHA, APK hashes, signer, AndroidTest package and installed APK bytes checked | DELIVERED source | Candidate not yet built |
| 06-02 | Exact running same-source native module, not only ZIP | `verify_matching_module`: ZIP + installed module hash **and live /proc/<pid>/exe hash** | FIXED HERE | Actual root/device process proof pending |
| 06-03 | Real authenticated auto-root, Mounts, browser, jobs and negatives | explicit per-case Android instrumentation (`BASE_LANES`) | DELIVERED harness | Device lanes unexecuted |
| 06-04 | Disposable lifecycle/reconcile with isolated registry and safe cleanup | `NativePersonalLiveTest`, runner stages an actually existing empty mountpoint with unique name and `rmdir` | FIXED HERE: absent directory would block Start | Device write profile pending |
| 06-05 | Disposable config/mount M3/CHECK/COPY/cancel | `WRITE_LANES`, target fixture verification, separate consent flags | DELIVERED harness | Device write profile pending |
| 06-06 | App-only cold restart and auto-root recheck | process PID change + repeat exact instrumentation lane | DELIVERED harness | Device run pending |
| 06-07 | No skipped/assumed tests, source-bound immutable evidence | exact instrumentation method, grammar + private log digest; checker reads and reparses original log | FIXED HERE: raw logs previously not independently bound/revalidated | Real receipts pending |
| 06-08 | Android 16 target/arm64 rooted device with SELinux Enforcing | rooted preflight API >=36, arm64-v8a, SELinux enforcing | FIXED HERE: prevent non-target API overclaim | Actual Android16 device pending |
| 06-09 | Separate explicit owner-scope approval & reproducible check | receipt log revalidation, exact source/bytes/signer/run/module/manager; all owner flags required | DELIVERED / FIXED HERE | Approval open until device PASS |
| 06-10 | Historical module approval not implicitly extended | dedicated APK scoped status, unchanged historical source receipt hashes | DELIVERED | New module may require separate source qualification |

## Defects found and resolved in this hotfix

1. **P0 | Disposable Mount Start fixture missing.** Daemon `internal/mounts/lifecycle/engine.go::verifyDestination` requires an existing, symlink-free directory. The full Android test generated a random mountpoint name but never created it. New host runner creates the uniquely named empty folder under `/storage/emulated/0/Download`, checks for collisions/symlinks, and `rmdir` only after the test, never `rm -rf` or force-unmount. Cleanup failure **blocks** the receipt.
2. **P0 | Stale running daemon could be approved.** Previously `verify_matching_module` verified the module ZIP and installed file, not the running image. Now requiring root-observed `pidof skybind` and `/proc/PID/exe` SHA-256 match. Unreadable PID/SELinux prevents approval; it cannot be guessed or waived.
3. **P0 | Per-lane evidence not independently revalidatable.** Prior receipts held instrumentation hash-shaped strings without retained raw output. Runner now writes private 0600 log files under a 0700 directory; both approval and later approval-check enforce exact relative path, SHA-256 and real instrumentation grammar and method. Failed original output is preserved for diagnosis.
4. **P1 | Foreground reconnect lost after background authenticated transport failure.** `SkybindSessionViewModel` now remembers disconnected authenticated background session and retries once on return to foreground; denied initial root permission and explicit user disconnect cannot auto-prompt loop.
5. **P1 | Android status bar occlusion on edge-to-edge UI.** Compose top header now uses explicit `statusBarsPadding()` and is test-tagged, preserving visible safe inset on Android15/16.
6. **P1 | Version/target receipt overclaim.** Native personal qualification requires Android API >=36 and native `arm64-v8a`; older API can still have source/external UI testing but does not satisfy this particular Android16 device receipt.

## Executable evidence recorded in this audit

- Baseline source clean exact commit and GitHub main SHA match verified. GitHub personal APK workflow confirmed upstream.
- `GOWORK=off GOTOOLCHAIN=local CGO_ENABLED=0 go test ./...` complete repository suite passed on audit baseline. Rerun on staged postimage before applying.
- Targeted native Python test suite and negative gates passed on baseline; staged regression source and log-tamper negatives passed. Confirm final counts from validation log bundled with overlay.
- Source-bound archive, preimage/postimage/negative corruption and simulated Devtool application are separate from actual Termux Devtool invocation.

## Release gates that must NOT be marked passed from source

1. Hosted GitHub personal APK workflow for **new post-hotfix commit**: compiled app + matching AndroidTest, signer, compiled manifest and version increase. At time of audit, none exists for the hotfix.
2. Installed same-source app/test **and** newly built/root-installed current-source Skybind module; hash the active daemon executable, not merely ZIP bytes.
3. Android16 exact runnable test lanes: read-only then isolated disposable full profile; cleanup, real runtime, root consent, lifecycle, config rollback, CHECK/COPY/cancel, negative mount behavior, cold relaunch.
4. Visual/accessibility screenshots: light/dark, 200% font, notch/landscape, launcher adaptive mask and notification; Android15 screenshot is an optional compatibility observation, not qualified by API36-only receipt.
5. Real root-manager denied permission review, FUSE/busy/writeback edge cases, and human review of active state. Tests that cannot be executed stay open rather than being claimed.
6. New exact candidate APK owner approval and repeatable `check`, with separate personal module qualification. No independent attestation is claimed.

**Decision:** all promised source pathways are present after these six fixes; APK compilation and on-device behavior remain unproven, not silently delivered. This audit must be re-evaluated if GitHub compile or device results expose further implementation defects.
