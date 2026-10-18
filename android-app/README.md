# Skybind Android — native M1 product-surface foundation

The repository's Android app is a real Kotlin/Compose multi-screen product surface, **not yet a connected Skybind client**. On current builds, the `UnpairedGateway` defaults to NOT_AUTHORIZED. `ReadOnlyCoordinator` always fails closed, and a disconnected state removes all stale server-derived remotes, jobs, mounts, and journal entries. Do not interpret the test-only fixture data as real daemon state.

**Screen boundaries:** Home shows connection and summaries; Browser searches remotely supplied names when authenticated; Jobs uses the authoritative job snapshot (running/queued/interrupted, then recent completed); Activity is a separate chronological journal with severity filtering and event cursor/gap semantics; More contains connection, mount availability and device/build information. Write, transfer, cancellation and mount controls remain visibly unavailable until a trusted broker and ownership-grant enforcement exist. No root requests, local root sockets, broadly accessible localhost endpoints, or secret copying.

## What M1 still needs

The app-to-daemon trusted transport and *actual* capability/health/remotes/jobs/event handshake remain an open M1 acceptance gate. Supply a privileged **authenticated** bridge selected under M0/R1, verify Binder UID + PackageManager signing identity and signed-grant expiry/revocation, then implement a `SkybindReadOnlyGateway` that calls the installed daemon's restricted typed API without exporting root or credentials. A fabricated `ONLINE` from a test fixture never grants production access. App-owned root shell is explicitly prohibited here.

## How to validate

- `python3 scripts/dev/android/m1_native_source_gate.py` — read-only source contract; no Gradle, Android SDK or device changes.
- `python3 scripts/dev/android/r1_b1c_security_source.py` — existing source suite plus M1 contract.
- `.github/workflows/skybind-android-apks.yml` — **sole** authorized Android APK/`androidTest` APK build. Never build with Gradle locally, including Termux/chroot.
- `NativeUiTest` is compiled into the separately uploaded `app-debug-androidTest.apk` and covers screens, data-source separation, safe unpaired state, browser filtering, disabled writes, and Activity recreation. It must be **run on device against a separately attested new APK pair** before any device PASS claim. The earlier B1-C6 result belongs to older installed bytes and stays historical.

Product roadmap remains M0–M5 from `SKYBIND_NATIVE_ANDROID_MASTER_PLAN_20261016.md`, and unified API A1–E + R0–R6 is authoritative. This change is an incremental M1 UI/state slice, not completion of M1 or M2, nor broker, device or release qualification.
