# Skybind M2-L3 — consolidated lifecycle continuation

**Source base:** verified GitHub `Mikeyphw/skybind/main` commit `7cb78fde4b07d3b9d34e2e78b5f2839fc4626115`, at the **already device-PASS** M2-L3 read-only negative acceptance. This bundle does not repeat or overwrite previously qualified receipts.

## Prior accepted evidence — immutable

| Scope | Hosted run | Artifact | Source | Reported outcome |
| --- | --- | --- | --- | --- |
| M2-L1 real RootService | 39352843961 | 12234555440 | c2cb64cdc3528c1de9814eb8ca4880b5aa778b8f | PASS, historical |
| M2-L2 real Compose | 39363846767 | 12239020736 | 6e36e46de1b28355296c5dd5367db98f7c4316d6 | PASS, historical |
| M2-L3 read-only negative paths | 39427946191 | 12267026065 | 7cb78fde4b07d3b9d34e2e78b5f2839fc4626115 | PASS, user-reported device receipt |

M2-L3 accepted user-reported path: `/data/data/com.termux/files/home/.local/state/skybind/ci-artifacts-device/ci-20261020T132620319975Z-dcf336cd/summary.json`; individual receipt: `/data/data/com.termux/files/home/.local/state/skybind/native-m2-live/m2-live-aec6ce97f57e45cda34efbe3314ec41f.json`. The **original device files remain on the device**; the summary in chat is not a local copy of the original. The selected-only M2-L3 runner's `m2_l1_device_qualified=false` and `m2_l2_device_qualified=false` are not invalidations of the older two receipts.

## This consolidated source implementation

1. **RootReadSession production hardening:** a late Binder callback cannot resurrect a superseded binding, and per-binding readers reject late snapshot/browse completion; failed RPC snapshots expire the app-owned binding on the main thread; cancellation rethrows instead of being disguised as an ordinary disconnection; RemoteException on browse triggers local transport teardown. Reconnect requires a fresh explicit session. No fallback root shell or socket exposure.
2. **M2-L3 `m2-transport-live`:** actual read-only RootService connection, controlled local transport loss via the production disconnect handler (not killed daemon), check duplicate callback suppression, fail-closed stale results, subsequent explicit successful reconnect. Single-test instrumentation strict parser, truthful BLOCKED/FAILED classification and individual source-/pair-bound receipt.
3. **M2-L3 `m2-process-live`:** external ADB coordinator, **independently opted into by both `--test m2-process-live` and `--allow-app-force-stop`**. Starts only the known Skybind unprivileged `MainActivity`, observes its PID, force-stops **only `io.github.mikeyphw.skybind`**, confirms absence, relaunches and checks a distinct PID and unauthenticated Compose UI via limited UIAutomator XML. Temporary uniquely named UI dump is deleted. Does **not** stop the privileged daemon or change root grants; if UI cannot be observed, result BLOCKED. The UI dump is not stored in receipts.
4. **Shared evidence gate:** immutable canonical hosted APK pair and signer verification, explicit same-signer install, per-lane receipt provenance/scope validation. No automatic process mutation, root revocation, data clear, reboot or remote write. Whole-product `device_qualified=false` and `release_qualified=false` remain unchanged.
5. **Source-only grouped Devtool DAG:** `./devtoolw m2-lifecycle-source` runs source contract, parser/negative regressions and hosted-only build policy. **No local Gradle or Android APK build** in this workflow.

## Exact next qualification

Build from new source commit on `.github/workflows/skybind-android-apks.yml` using GitHub Actions. Once that hosted run has succeeded and the exact APK pair has been checked/installed, qualify separately:

```sh
./devtoolw m2-lifecycle-source
git push origin main
gh workflow run skybind-android-apks.yml -R Mikeyphw/skybind --ref main

# Replace RUN_ID with the NEW successful hosted run matching exact HEAD.
python3 -B scripts/devtool/ci_artifacts_device.py --run-id RUN_ID \
  --expected-sha "$(git rev-parse HEAD)" --serial emulator-5554 \
  --install --test m2-transport-live

# Only if explicitly consenting to app-only process termination:
python3 -B scripts/devtool/ci_artifacts_device.py --run-id RUN_ID \
  --expected-sha "$(git rev-parse HEAD)" --serial emulator-5554 \
  --test m2-process-live --allow-app-force-stop
```

The previous `m2-negative-live` PASS remains valid as *historical evidence*; do not rerun it just to aggregate flags. Neither of these new acceptance scopes tests **real daemon crash**, **KernelSU grant refusal/revocation**, concurrent stale remote-cursor requests beyond the app generation guard, cross-UID BKX/chrootctl consumption, transfer cancellation/reconciliation, or release readiness. The integrated A1–E/R0–R6 roadmap still governs those separate milestones.

## Remaining M2-L3 / next phases

- Independent root-manager denial requires manual/operator consent and explicit proof (no grant mutation in default lanes).
- Actual daemon stop/recovery is deferred: live root daemon and queued-work state must not be disturbed solely for automated acceptance.
- UI edge cases (unavailable remote, unsupported API, event cursor gaps, empty directory, narrow layout) warrant next reviewable acceptance; this overlay deliberately avoids inventing fixtures as real device qualification.
- M3 owned-job, guarded operation previews and unified API/provider work remain open; no fork of the existing 57 frozen CFS1 operation catalog.
