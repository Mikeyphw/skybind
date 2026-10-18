# Skybind B1-C — attested hosted APK device provenance and instrumentation

Date: 2026-10-17. B1-C1 source campaign. **Never reuse this receipt to qualify a changed APK.**

## Locked hosted input

- Repository: `Mikeyphw/skybind`
- Hosted source SHA: `1b808119720ed3c042ffc2a8fa84ebe313697eb8`
- GitHub run: `39070051696`
- Devtool ACTIONS-06 pipeline: `be9ee025156643fe9a5c21d577dd0d2f`
- H4 result: `PASS_HOSTED_PAIR_INSPECTED_NOT_DEVICE_QUALIFIED`
- Immutable receipt: `build/evidence/r1-android-hosted/<pipeline>/attestation.json`
- Exact APK pair in Devtool's authenticated GitHub archive: `app-debug.apk` and `app-debug-androidTest.apk`

## Safety and qualification boundaries

The runner uses **the original hosted APKs**, not rebuilt APKs after this device-runner overlay changes Git HEAD. The runner independently checks the recorded attestation fields, finds exactly one matching ZIP by SHA-256 in the canonical Devtool download store, validates exact APK filenames and APK SHA-256 hashes, discovers a uniquely authorized ADB device, and compares **both installed base APK bytes** to those hashes via `adb pull` (never using package name alone as identity proof). It never installs, uninstalls, replaces, clears, roots or reboots by default.

`--install-missing` is an explicit opt-in, allowed **only when both packages are absent**. Uses ordinary `adb install` without `-r` or bypasses, then re-pulls and verifies both installed APKs before tests. If an app or test APK is already present but different, the gate fails closed and refuses replacement. If ADB cannot access installed APKs, the gate reports `BLOCKED` rather than assuming provenance. If multiple physical transports appear, use `--serial`; two ADB transports are not automatically two independent devices.

Instrumentation is restricted to exactly two methods in the existing, attested test APK:

- `ScaffoldTest#appStartsWithoutBrokerOrRoot`
- `UidPackageEvidenceTest#deniesUnknownOrUnpinnedCaller`

The runner accepts only two unique successful AndroidJUnitRunner method results plus final `INSTRUMENTATION_CODE: -1`; it records structured, sanitized JSON without app data or full logs. Existing test APKs contain **negative local PackageManager helper tests only**, not privileged broker attestation or cross-UID SELinux acceptance. Thus even `PASS_B1C_DEVICE_INSTRUMENTATION` has `device_qualified=false`, `release_qualified=false`, `production_broker_enabled=false`.

## In Termux (no build or GitHub dispatch)

```sh
cd ~/Code/skybind
# First, non-mutating installed APK-byte preflight:
./devtoolw r1-device-provenance

# Only if both apps are already installed from the exact trusted APK pair:
./devtoolw r1-device-instrumentation

# If there is exactly one authorized device and BOTH APKs are absent,
# opt-in to a first-time install and then both tests (NO replacement allowed):
python3 scripts/dev/android/r1_b1c_device.py --mode instrument --install-missing

# For multiple ADB devices, select one explicitly:
python3 scripts/dev/android/r1_b1c_device.py --mode instrument --serial YOUR_SERIAL
```

Outputs: uniquely named, immutable JSON receipts under `build/evidence/android/b1c/`. Failure/blocked receipts remain. Preserve the hosted H4 attestation and old failed GitHub Actions evidence. Don't rerun GitHub CI just to run an unchanged APK. The source overlay itself is source-only and produces **no** device acceptance results.

## Later B1-C gates (not claimed here)

Trusted privileged Binder/PackageManager attestation authority, authenticated Go handoff, BKX caller pinning, chrootctl sealed module caller, real cross-UID operations against isolated disposable resources, and production-configuration review remain separate outstanding gates. Do not enable the broker listener or grant production access on the strength of this source/Android UI test result.
