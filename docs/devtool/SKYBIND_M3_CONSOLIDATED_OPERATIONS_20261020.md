# Skybind M3 — consolidated, proof-bound Android operations slice

Date: 2026-10-20. Source preimage: `Mikeyphw/skybind` `main`
`def2d8722bb5b2c0419db259f291814a3ba723c9`.

## Preserved, independently completed evidence

- M2-L1 real RootService read/browse/rebind, run `39352843961` (historical PASS).
- M2-L2 real Compose navigation, run `39363846767` (historical PASS).
- M2-L3 read-only negative boundaries, run `39427946191`, artifact `12267026065`,
  SHA `7cb78fde4b07d3b9d34e2e78b5f2839fc4626115` (historical PASS).
- M2-L3 transport and app-only cold launch, run `39442535828`, artifact `12274437837`,
  SHA `def2d8722bb5b2c0419db259f291814a3ba723c9` (historical PASS).
- These later run summaries were supplied by the user; the original JSON receipt files
  remain on the Android device, and their exact paths must not be forged or overwritten.
- Historical PASS status is NOT a claim that M3 changes preserve Android behavior
  without compilation and new device acceptance on the resulting source SHA.

## What's actually implemented in this single source overlay

- The old `query()` Binder method remains strictly read-only and calls daemon `query`
  class with the existing allowlist, peer UID check, owned-root socket paths, and
  bounded request/reply sizes.
- New private Binder methods: `previewJob(sessionId, jobName)`,
  `startPreparedJob(sessionId, previewId)`, `cancelOwnedRun(sessionId, runId)` and
  `forgetSession(sessionId)`.
- Preview calls existing typed daemon `job.run.preview`; accepts only configured
  `check` and `copy` jobs where daemon `destructive=false`; `sync` remains locked.
- Root service retains the 64-hex daemon proof privately and returns a random
  opaque 90-second preview ticket. Only an explicit UI confirmation consumes it;
  the daemon revalidates the one-use proof against name, job definition digest,
  registry revision, and operation action. Any unknown/expired/cross-session ticket
  is denied without running a command.
- A `copy` preview requires extra UI consent warning about destination writes.
  `check` requires confirmation too. Neither executes automatically on connection,
  navigation, or refresh.
- Cancellation is restricted to a valid daemon run ID returned by this broker
  during the current app session. It cannot cancel other clients' or pre-existing
  runs. Closing/disconnecting drops previews and owned-cancel authority but does
  **not** stop a job that has already been accepted by the daemon.
- Jobs UI lists the configured daemon jobs separately from the active and recent
  runs. Rich progress fields (bytes, total, speed, ETA, percent and file counts)
  come from `jobs.status` and are validated as numeric and nonnegative. Only
  active session-owned runs are auto-refreshed every three seconds.
- Launch transport ambiguity never triggers automatic retries; user must refresh
  the authoritative job list and issue a brand-new preview if appropriate.
- Android instrumentation `LiveM3PreviewAcceptanceTest` inspects a **real**
  configured check/copy job and requests a preview, but NEVER starts or cancels.
  Missing eligible job is **BLOCKED**, not a successful test. The opt-in
  `m3-preview-live` lane binds to an authenticated GitHub-built/installed APK pair.

## Deliberately not qualified here

- **Not** a general-purpose root RPC or exported BKX/chrootctl broker.
- **Not** a permission to start sync, edit schedules, create transfers, cancel
  unrelated jobs, terminate the daemon, revoke root grants or publish a release.
- **Not** real-device confirmation of a write-capable `copy` job; that needs
  a separately authorized disposable fixture, canonical source/destination
  identity, and explicit cleanup policy. No arbitrary user data is test data.
- Source-level PASS is not hosted Kotlin compilation, installed APK acceptance,
  full M3, unified A1–E/R0–R6 compatibility, or release qualification.

## Post-apply workflow

1. `./devtoolw m3-operations-source` validates the source, negative regression,
   and GitHub-only APK policy. It neither builds nor installs APKs.
2. `git push origin main` then `gh workflow run skybind-android-apks.yml -R Mikeyphw/skybind --ref main`.
3. After hosted success, on the real Android device use the **new** run ID and
   exact source SHA, not any historical M2 run:

```bash
python3 -B scripts/devtool/ci_artifacts_device.py \
  --run-id NEW_GITHUB_RUN_ID --expected-sha "$(git rev-parse HEAD)" \
  --install --test m3-preview-live
```

The explicit `--install` authorizes only a same-signer APK upgrade; the preview
lane cannot launch a copy or cancel. A real eligible job is necessary. The CI
receipt must have `m3_preview_device_qualified=true` **only** for the selected
preview lane, and keep `device_qualified=false`, `release_qualified=false`.

## Next milestone after this overlay

Review actual GitHub Kotlin build and instrumented preview receipt. Then author
and qualify a separate opt-in test-owned disposable copy/check job fixture before
marking write-capable M3 acceptance. Continue the unified roadmap for other
planned operations, rclone-native provider compatibility, BKX and chrootctl.
