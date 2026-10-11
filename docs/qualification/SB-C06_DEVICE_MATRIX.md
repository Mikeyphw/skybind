# Skybind SB-C06 — Android release qualification matrix

This is an executable-device-test *framework*, not evidence of real-device passage.
Neither a root-shell file read nor `go test` proves Android application visibility.

## Required real-device evidence (per supported manager and provider)

- Physical ARM64 device fingerprint, Android API level, supported root-manager
  identity/version; no emulator substitution.
- Verified NewFuture **and** bclone runtime bytes, exact release ZIP checksum,
  FUSE helper presence, module install/startup state and daemon readiness.
- Successful ordinary-app `org.skybind.probe` write + readback of a 32-byte
  unpredictable nonce **inside the configured mount target**, with app UID,
  readback count, exact target path, screenshot/log attachments and collection
  recorded in a Devtool device run. Root-shell read/write does not qualify.
- Exact target versus Android storage alias distinction; primary/secondary users,
  app namespace churn, protected namespaces, stale proof/rollback.
- Wi-Fi/unmetered/metered/offline, battery/charging/low cache space, stop/restart,
  daemon crash/reboot, sleep/wake, failed credentials, corrupted cache, orphan
  mounts, interrupted jobs, cancelled destructive operations and uninstall.
- Original UI: real WebView and standalone screenshots at narrow/wide layouts,
  navigation, dialogs, wizard, keyboard/accessibility and failure states.
- Longer running idle/recovery endurance on each *claimed* manager combination.

## Ordinary-app probe

`tests/device/probe-app` is a minimal ordinary Android Activity (no root,
MANAGE_EXTERNAL_STORAGE, or privileged storage permissions). Build it with the
pinned Android SDK/Gradle toolchain if available, install the APK through an
explicit Devtool device workflow, and then collect evidence with
`scripts/dev/device/skybind_device.py`. The collector verifies that the UID,
nonce, byte counts and tested configured path match the app process' own result.
The `run-as` command is used solely to retrieve the Activity's private receipt.
**Running `run-as` itself is never evidence of app namespace access.**

A raw collector JSON is *not* a sealed result. Independent gate verification must
link it to immutable Devtool run-store evidence, the tested APK, source revision,
module ZIP and exact physical-device fingerprint, and attach test-app stdout,
logs and screenshots. All claimed device requirements remain unqualified until
that independent process succeeds. No release/seal may be asserted from a
user-supplied receipt alone.
