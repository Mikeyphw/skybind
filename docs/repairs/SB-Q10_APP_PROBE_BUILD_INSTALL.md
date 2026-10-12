# SB-Q10 — Ordinary Android UID probe build/install

Adds an explicit **debug** Android-app-probe build/install workflow to the Skybind
Devtool wrapper. The app's existing `tests/device/probe-app` source is reused
*unchanged* (package `org.skybind.probe`, SDK 35, debug auto-signing by Gradle).
This overlay does not change the already-working SB-Q07/SB-Q08 FUSE module.

## Requirements

- Skybind checked out at `~/Code/skybind`, including existing Q09/SB-C06 probe sources.
- Termux on Android, Devtool wrapper/runtime, root granted by KernelSU, and the
  managed Android builder at `~/.local/share/devtool/runtime/android/build-apk`.
- SDK Platform **35** and Android Gradle Plugin **8.7.3**, cached/available.
  Builds are **offline by default** and will fail clearly if the toolchain
  cache is missing. The fallback is an already-installed `gradle --offline`.
- At least ~2 GiB free on the build volume (3 GiB targeted by the helper).
- No manual APK signing setup is needed for the debug variant. Never ship this
  debuggable build as a production or independently attested release.

## One command (after applying overlay)

```sh
cd ~/Code/skybind
./devtoolw app-probe
```

The command builds `:app:assembleDebug`, checks APK structure and SHA-256,
records a local hash/source receipt, then installs *only* `org.skybind.probe`
using root's `/system/bin/pm install -r`. It stages a short-lived APK in
`/data/local/tmp` and removes it after attempting installation. The installer
**never uninstalls existing app data** to resolve a signature conflict; any
signature mismatch fails visibly. It checks the installed app's UID is
unprivileged (>=10000). It neither launches the probe nor writes to the mount.

Or build and install separately:

```sh
./devtoolw build-app-probe
./devtoolw install-app-probe
```

Debug APK and receipt live at:

```
build/app-probe/skybind-app-probe-debug.apk
build/app-probe/build-receipt.json
```

If a prebuilt version signed by another debug key is present, the install may
fail with `INSTALL_FAILED_UPDATE_INCOMPATIBLE`. The script intentionally does
not uninstall/reinstall around the signature or grant storage bypasses.

## Next: run the actual *ordinary-app* read/write qualification

With the mount RUNNING, use the separately installed Q09 collector:

```sh
~/.local/bin/skybind-q09 app-probe --yes
```

The Q09 collector asks for consent again, launches the **actual app process**,
then collects its private receipt via `run-as`. A root-shell write, an APK
install and an app UID number alone are **not** app read/write evidence.
Scoped storage/Android namespace denial is a valid diagnostic failure and
must not be bypassed just to force a PASS. Upload the resulting Q09 app-probe
ZIP for analysis.

## Scope and validation

- Preflight requires the original, unchanged probe sources and blocked release
  policy. Overlay apply requires a clean Git tree and uses atomic rollback.
- Local validation uses 14 Python tests for the pre-existing device contract
  plus Q10 command wiring, source checks, receipt integrity and simulated
  installation failure/success. Simulated tests do not certify device install.
- No Android APK was built or installed by the overlay packaging environment.
- G01–G08, device attestation and independent final release signing remain
  blocked / `NOT_ISSUED`.
