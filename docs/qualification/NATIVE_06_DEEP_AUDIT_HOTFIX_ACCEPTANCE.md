# NATIVE-06 deep-audit source hotfix — operator handoff

Baseline **must** be exact clean Skybind commit `02bf99fb47a5fa7c8509aa672f0438142123a621`, tree `278c3a950c31763b3a3a1fc399293689c741563a`. The Devtool overlay has atomic validation and intentionally changes Android app and device-runner source, invalidating old APK evidence.

Detailed promise-by-promise evidence: `docs/qualification/NATIVE_00_06_DEEP_PROMISE_AUDIT_20261023.md`.

## Scope of this hotfix

- Fix Android16 status-bar-safe header and narrowly scoped auto reconnect after background authenticated binder loss.
- Make disposable lifecycle acceptance create an empty mountpoint before test, detect collision/symlink and clean using only safe `rmdir`.
- Prove installed module binary AND **live running process image** match candidate bytes and commit, blocking stale daemon.
- Record full instrumentation logs privately (0600 under 0700), digest into per-lane receipt and re-verify exact method/outcome at owner approval and later approval-check.
- Reject wrong API (<36), ABI, assumptions/skips and old receipt schema; extend negative tests.
- Append findings to cumulative improvements ledger.

## Qualification sequence (after overlay successfully applies)

1. Confirm the updated source commit and push to remote `main` only after confirming clean source and correct Git remote. `git status --short; git rev-parse HEAD; git push origin main`. The hotfix changes the *source SHA*, so do not dispatch an APK for old `02bf99f` and call it qualified.
2. Determine installed APK versionCode; choose a strictly larger integer (never assume `2`). `gh workflow run skybind-personal-apk.yml --repo Mikeyphw/skybind --ref main -f version_code=<INCREASING_INTEGER>`; inspect run ID and `gh run watch -R Mikeyphw/skybind <RUN_ID>`.
3. Download verified hosted app+AndroidTest using `python3 scripts/dev/android/personal_apk_device.py fetch --run-id <RUN_ID>`. Use `device --folder <FOLDER> --serial <SERIAL> --source-sha <CURRENT_SHA>` for inspection, then explicit `--install` only after signer/version/in-place compatibility is confirmed. **Never** uninstall or clear app data.
4. Build same-source personal bclone module using `./devtoolw personal-release` from current clean checkout. Keep existing personal module approval historical; new module is different bytes. Verify `PERSONAL_BUILD.json`, ZIP/hash, root-manager install, reboot if required; do not silently install or reboot.
5. With app/test pair and module running on Android16 rooted ARM64/SELinux Enforcing, run **read-only profile first** (no mutation flags). Verify status `PASS_NATIVE_PERSONAL_READONLY_ONLY_NOT_QUALIFIED` and original, privately retained logs; any SKIP is a failure.
6. Full profile only on backup/disposable isolated test device with existing configured remote and independently prepared M3 CHECK/COPY fixtures; explicit allow-disposable-config/jobs, allow-app-force-stop, allow-global-reconcile. The runner now manages a test mountpoint without `rm -rf`; if cleanup fails, inspect manually and DO NOT force remove. Require `PASS_NATIVE_PERSONAL_DEVICE_FULL` and `device_qualified:true`.
7. Only after inspecting source, launcher, root manager, mount UX, cold/reconnect, all exact PASS method logs and matching daemon image, run `... native06_personal_acceptance.py approve` with explicit UI/root/mount/personal-scope/untested-manager acceptance flags; then `check`. Preserve the receipt, private logs, source hash and GitHub run ID.

See existing `docs/qualification/NATIVE_06_PERSONAL_APK_ACCEPTANCE.md` for complete command examples and all consent options. Real GitHub compile / physical device tests / explicit owner approval are pending — local source regressions do not qualify an APK.
