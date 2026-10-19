# Skybind M2-L1 — live read-only root-service acceptance

The prior 19/19 instrumentation result verifies fixtures and UI behavior, **not** live daemon integration. This opt-in single-case gate verifies a real user-authorized app-owned libsu RootService bound to the existing Skybind daemon, a bounded listing on exactly one configured remote, stale-data cleanup on unbind, and a rebind/authoritative refresh. No test fixtures or privileged host shell are involved.

## Canonical GitHub APK/device entry point (adapted from Cinderbox)

`python3 -B scripts/devtool/ci_artifacts_device.py` is now Skybind's supported
CI-artifact download, byte/certificate verification, optional same-signer
installation and explicit device-lane launcher. The prior standalone
`scripts/dev/android/m2_live_device.py` is retained as the internally invoked
source-bound M2-L1 acceptance worker; do not duplicate its safety checks.

1. Apply this combined M2-L1 Devtool overlay at the pinned clean source and push.
   Keep GitHub-hosted Gradle compilation only.
2. Dispatch `gh workflow run skybind-android-apks.yml --ref main` and record its
   successful run ID. The hosted artifact bundles exactly
   `app-debug.apk`, `app-debug-androidTest.apk`, and
   `android-build-manifest.json`.
3. List supported reviewed lanes:
   `python3 -B scripts/devtool/ci_artifacts_device.py --list-tests`.
4. **Only verify** an already-installed matching pair (the default):
   `python3 -B scripts/devtool/ci_artifacts_device.py --run-id RUN_ID`.
5. For a first install or update, explicit opt-in is required. It refuses
   replacements if existing signer fingerprints differ, package installation
   state is partial/ambiguous or GitHub source/manifest/hash/certificate
   checks fail:
   `python3 -B scripts/devtool/ci_artifacts_device.py --run-id RUN_ID --install`.
   There is **no uninstall, downgrade, data clear, reboot or backup**.
6. After app and test APKs are installed, qualify the real root-service lane:
   `python3 -B scripts/devtool/ci_artifacts_device.py --run-id RUN_ID --test m2-live`.
   Optional `--remote REMOTE` selects one configured remote (without writing
   its name to the receipt); optional `--serial SERIAL` chooses an authorized
   device. Test execution is **never implicit**.
7. For M2-only identity re-check: `--test m2-preflight`. Both lanes can be
   explicitly selected with repeated `--test` arguments.

All source/runner checks require a clean local HEAD matching the successful
GitHub workflow run. Pair cache: `~/.cache/skybind/hosted-RUN_ID/`.
Sensitive-free driver receipts: `~/.local/state/skybind/ci-artifacts-device/`;
per-lane M2 receipts: `~/.local/state/skybind/native-m2-live/`.
The CI API returns an artifact ZIP digest, but `gh run download` extracts the
ZIP without retaining the original archive; this launcher independently
verifies both APK byte SHA-256 values and both signing certificates against
its source-bound hosted manifest and local pinned certificate. It does not
claim an independent downloaded archive ZIP digest check.

The root manager must authorize the app interactively. No scripted approval.
A missing daemon, root grant or configured remote blocks the lane; an actual
API/browse regression fails the lane. A passing M2-L1 receipt qualifies **only**
the live read-only root-query/browser/rebind gate, not complete app release.

The prior 19/19 non-live instrumentation result remains historical evidence.
There is no need to repeat it automatically for every M2-L1 attempt.

**Not covered:** on-screen UI interactions with actual remote, root denial prompt automation, deliberate process death/daemon termination, external cross-UID BKX/chrootctl broker grants, write operations, or release qualification. Those require separate acceptance gates; no deferred M0–M8 manual replay is requested.
