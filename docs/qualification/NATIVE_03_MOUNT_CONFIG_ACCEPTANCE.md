# Skybind NATIVE-03 — complete implementation, independent qualification pending

**Target source:** exact committed NATIVE-02 checkout. **Status:** all NATIVE-03 implementation promises are implemented in this revised overlay; a real Android build, daemon upgrade and device acceptance remain external qualification gates. No preexisting personal approval, Go test, or source test is substituted for them.

## Promise-by-promise delivery audit

| Explicit promise | Evidence/implementation | Implementation | External acceptance |
|---|---|---|---|
| Four-step source / destination / behavior / review | `MountConfigEditor.kt`, `MountDraft`, saved session state | DELIVERED | APK / UI device pending |
| Create / edit / delete | Separate AIDL methods, root-service full-registry reconstruction; one-use `config.validate` → `config.preview` → `config.apply` | DELIVERED | Disposable live config test pending |
| Configured remotes, 21 typed public fields, advanced VFS/cache/network/battery | Local `fieldErrors`, root strict draft, daemon normalized registry | DELIVERED | Live source/path checks pending |
| Preserve all unrelated entries and reject revision drift | Root server reconstructs from `config.snapshot`; daemon's revision/digest proof | DELIVERED | Concurrent-change device test pending |
| Structured backend field-level validation | `config.FieldValidationError` → bounded `protocol.Fault.FieldErrors` → root service only returns whitelisted field+code for target mount → `ConfigFieldValidation` → per-field UI messages. Invalid config still fails `ok:false`; no raw paths, credentials or provider messages forwarded | DELIVERED | Kotlin compiled/runtime integration pending |
| Full native rollback of previous-known-good registry | Separate `previewRollbackMountConfiguration` / `applyRollbackMountConfiguration` AIDL; daemon-owned candidate/proof; UI shows *all* affected mounts; explicit checkbox; ticket consumed before one attempt | DELIVERED | Live rollback result/health pending |
| Rollback busy/FUSE/writeback safety and crash recovery | Existing daemon `RollbackConfig` prepare check, atomic pending record/recovery, plus new Go test for prepare refusal and consumed proof | DELIVERED | Actual busy writeback device test pending |
| Foreign-session, expiry, replay, stale revision guards | Independent server-side config and rollback ticket guards, 60-second expiry, caller UID/signer verification, negative source tests | DELIVERED | Binder negative device test pending |
| No arbitrary root RPC, no secret editing, no implicit mutations | Read-only query allowlist unchanged; exact Binder methods only; no raw arguments/proofs sent to UI; no config mutation during connection/refresh | DELIVERED | Device observation pending |
| Native automated integration | `NativeMountConfigContractTest.kt` and explicitly opt-in `NativeMountConfigLiveTest.kt` test create/edit/rollback/delete with disabled test-owned mount, preserving other entries and cleaning up | TESTS DELIVERED | Device execution pending |
| Full Go/backend regression | `go test ./...`, detailed validation fault tests, daemon wiring tests, rollback prepare refusal | PASS LOCAL | N/A |
| Host Gradle APK/test APK build + device-specific signing | Existing `skybind-android-apks.yml` must be run at the new exact post-overlay SHA | INFRASTRUCTURE EXISTS | NOT EXECUTED |
| Fresh personal-release qualification | Historical approval cannot cover changed `internal/` and `android-app/` | RELEASE GATE PRESERVED | OPEN |

The original NATIVE-03 package should **not** be applied before this replacement. This package folds in both missing functional promises; it is **not a second overlay atop NATIVE-03**.

## Device qualification (required after application)

1. Push the exact clean post-overlay commit. Use `skybind-android-apks.yml` to produce an authenticated app/test APK pair for that commit; inspect Gradle results and signer provenance.
2. Rebuild/install the corresponding **changed daemon module** through a new personal build and explicitly authorized install on a backed-up, disposable test device. Do not combine the new APK with an old daemon and treat the outcome as acceptance.
3. Use `ci_artifacts_device.py` with exact run ID, expected SHA, selected serial and `--install` only if needed; verify both installed APK hashes and signatures.
4. Run old M2/M3 read-only and fresh full lanes as applicable. For the new explicitly authorized test, specify a configured remote and test-only device:

```sh
adb -s "$SERIAL" shell am instrument -w -r \
  -e skybind.native.config.allow_disposable true \
  -e skybind.native.config.remote "$TEST_REMOTE" \
  -e class io.github.mikeyphw.skybind.NativeMountConfigLiveTest \
  io.github.mikeyphw.skybind.test/androidx.test.runner.AndroidJUnitRunner
```

The test fixture is a disabled, private-name entry and does not start FUSE, but temporarily modifies the daemon's registry. Do not run on a device with irreplaceable configuration. Stop and inspect if cleanup fails. A skipped test is not a pass. Separately record stale-revision, foreign session, busy writeback, crash recovery and root-manager behavior on the target rather than conflating Go unit tests with device observations.
5. Re-run the personal policy evidence gate against the changed product source. Approve any new personal artifact only after the exact APK and module pair are reviewed and qualified.

## Security invariant summary

- API remains typed; client never supplies rollback candidate JSON or a reusable daemon proof.
- Rollback affects the entire prior registry and is labeled accordingly in the UI.
- Daemon-only validation details contain constant codes and field names; failure still returns `ok:false`.
- Validation errors are scoped by candidate index; data from other registry entries is not promoted as an error for the user's draft.
- A consumed ticket is never automatically retried on ambiguous transport outcomes.
- No unrelated production mount is created or started automatically on launch.
