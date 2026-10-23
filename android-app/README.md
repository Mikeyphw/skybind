# Skybind — native Android Filesystem Control

Skybind is a rooted Android control client for the Skybind daemon. It provides Home, Mounts, Browser, Jobs and More (including Activity and diagnostics) using Jetpack Compose. It is not a generic root shell or a separate filesystem implementation.

## Connection and safety

- The app automatically attempts to bind its app-owned `libsu` RootService on foreground entry when auto-connect is enabled. Persistent root permission is controlled by KernelSU/Magisk/APatch, **not** silently granted by the app. Denial and transport loss fail closed with an explicit Retry/Disconnect option.
- RootService verifies caller/package/signature and daemon peer identity; remote file browsing remains bounded and read-only. Jobs and mount operations use dedicated narrowly typed RPC and Binder interfaces.
- Mounts are first-class: query live status, preview and confirm Start, Stop, Restart and Reconcile; create/edit/delete configuration with daemon validation/revision/one-use proof, field diagnostics and whole-registry rollback. All writes need explicit user consent. Nothing mutates mounts or starts jobs during app launch/reconnect/refresh.
- BKX background PackageManager authority is a **separate** opt-in foreground service with its own controls. Automatic root binding never starts BKX in the background.

## App identity

- Package ID: `io.github.mikeyphw.skybind` (preserved for in-place upgrades).
- Launcher label: `Skybind` via `@string/app_name`.
- Existing linked-S vector/adaptive launcher icon (including Android themed monochrome mask), platform splash icon, and dedicated white Skybind notification status icon.
- Personal builds are **non-debuggable** and branded `0.2.0-personal.<versionCode>`, with an explicit version code greater than one. Debug builds retain `0.1.0-dev`/versionCode 1 and remain distinguishable as debug artifacts.

## GitHub-only APK builds

The repository prohibits local Devtool APK compilation: both app and instrumentation APK are built by GitHub Actions. See `scripts/dev/android/verify_cloud_build_only.py`.

- `.github/workflows/skybind-android-apks.yml` retains the older **debug** lane. It uses a persistent GitHub signing keystore and fails closed on absent/rotated certificate pins.
- `.github/workflows/skybind-personal-apk.yml` is the **personal candidate** lane. Dispatch manually from `main` with an explicit higher `version_code`. Its `personal` build type is non-debuggable; the AndroidTest APK is separately assembled for that same personal variant. The **same existing persistent signing certificate** is reused intentionally for in-place upgrade continuity. Never silently rotate it.
- The personal workflow publishes exactly three files: `app-personal.apk`, `app-personal-androidTest.apk`, `PERSONAL_APK_MANIFEST.json`, in the `skybind-personal-apk-candidate-unqualified` artifact. The JSON binds exact byte digests, compiled package identities, signing cert, version, permissions, privileged AIDL/source inventory, GitHub SHA/run and toolchain. It always reports **`PERSONAL_APK_CANDIDATE_ONLY`**; no device or independent release qualification is claimed.

## Safe download and device staging

The owner should have `gh`, `aapt`, `apksigner`, `adb` and the existing local public signer pin (`~/.local/share/skybind/signing/signer-sha256.txt`). After GitHub builds the personal candidate:

```bash
python3 scripts/dev/android/personal_apk_device.py fetch --run-id <GITHUB_RUN_ID>
python3 scripts/dev/android/personal_apk_device.py device \
  --folder "$HOME/Downloads/Skybind-Personal-APK-<GITHUB_RUN_ID>" \
  --serial <ADB_SERIAL> --source-sha <EXACT_GIT_SHA>
```

Both commands are **non-installing**. The first authenticates the GitHub run and validates the signed byte pair. The second inspects the currently installed app/test pair, compares the locally pinned signer and requires a strictly higher version code for upgrades. To authorize an in-place install, repeat the `device` command with an explicit `--install`. It never uninstalls, clears data, requests `-d` downgrade, executes root shell, or force-stops the app. If app/test installation partly fails, inspect the device state before attempting recovery.

A different installed signer blocks an in-place update: a migration would require separate user review and must not be silently performed. **Do not confuse the personal APK with the separately approved personal module ZIP.**

## Release qualification

All new Android source from NATIVE-00/01 through NATIVE-05 requires fresh GitHub APK provenance and real-device positive/negative acceptance, including new Mounts/config/rollback and automatic root flows, and an API 36 test. Existing historical nine-lane APK receipts and the older personal module approval do not qualify new app bytes. `docs/qualification/NATIVE_05_PERSONAL_APK_ACCEPTANCE.md` lists every promise and gate; NATIVE-06 covers the final device checks and separate owner approval.
