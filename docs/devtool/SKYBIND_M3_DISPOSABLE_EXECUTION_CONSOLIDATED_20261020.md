# Skybind M3 — consolidated disposable execution and owned cancellation

## Ground truth / preserved evidence

- Historical M2-L1/L2/L3 read, UI, negative, transport, and cold-launch receipts remain passing; do not rerun them for this acceptance.
- M3 preview **PASS**, artifact `12287538216`, run `39472233849`, SHA `af35406346680e2a813811127a88f07cee381053`, `m3_preview_device_qualified=true`, qualified scope `M3_REAL_DAEMON_JOB_PREVIEW_ONLY_NO_EXECUTION`.
- This milestone creates **new scopes only**. Passing source tests are not device qualification. No release-qualified claim.

## Scope and threat model

- `LiveM3DisposableAcceptanceTest` may call privileged `job.run`/`operation.cancel` through the existing typed, session-scoped RootService broker only after an **explicit selected test** AND **explicit launcher authorization**.
- A fixed fixture name, exact `check` kind, exact source and destination under `/storage/emulated/0/Download/.skybind-m3-disposable`, and daemon preview identity are verified **before** launch. No `sync`/`copy`, mount, arbitrary RPC or raw root shell is used by instrumentation.
- The fixture uses **manual-only `interval_seconds=0`**. The helper's default is inspect-only, and `prepare/remove --apply` explicitly authorizes register/cleanup. Source and destination contain matching deterministic 4-KiB files; check must not modify them.
- Only the run ID returned from this app session may be canceled. A foreign sentinel ID must be refused. Completing before cancellation results in **BLOCKED_CANCEL_RACE**, not artificial PASS.
- An in-flight job is not cleaned up by blind force-stop. Remove is refused while the fixture has an active running/queued job; cleanup rejects unknown or modified files and will never recursively delete a user directory.
- The client reads authoritative `jobs.status` and `operation.events`, demands terminal COMPLETED for check, and demands terminal CANCELLED for cancel. Both demand observed matching run event, and require the session to be cleared after close. No synthetic results.
- The runner verifies exact successful GitHub commit/artifact, SHA-256 and signer of both APKs, installed byte equality; never compiles locally. Selection is per lane: `m3-execute-live`, `m3-cancel-live`. Two independent `qualified_scope` values; release remains false.

## Runbook (Termux on emulator-5554, no implied root in adb shell)

1. Apply consolidated Devtool overlay to clean SHA `af35406346680e2a813811127a88f07cee381053`.
2. Run `./devtoolw m3-disposable-source`, `git push origin main`, then dispatch hosted `skybind-android-apks.yml`.
3. Create deterministic fixture under user control:
   `python3 -B scripts/dev/android/m3_disposable_fixture.py prepare --apply --files 512`.
4. Once new GitHub run succeeds, assign its ID to `$RUN_ID` and run:

```sh
python3 -B scripts/devtool/ci_artifacts_device.py \
  --run-id "$RUN_ID" \
  --expected-sha "$(git rev-parse HEAD)" \
  --serial emulator-5554 \
  --install \
  --test m3-execute-live \
  --allow-disposable-job-execution
```

5. Run exact session-owned cancellation only after reviewing fixture scope and authorizing it separately:

```sh
python3 -B scripts/devtool/ci_artifacts_device.py \
  --run-id "$RUN_ID" \
  --expected-sha "$(git rev-parse HEAD)" \
  --serial emulator-5554 \
  --skip-install \
  --test m3-cancel-live \
  --allow-disposable-job-execution \
  --allow-disposable-job-cancellation
```

6. Before cleanup, inspect active jobs, then explicitly remove only the owned fixture:
   `python3 -B scripts/dev/android/m3_disposable_fixture.py remove --apply`.

**Warning:** Real `check` execution can consume device CPU, I/O and job history. The cancellation test may be BLOCKED when the check is too fast. Increasing `--files` changes the disposable workload and should only be done after owned fixture removal and explicit recreation. Never target normal configured jobs. No automatic daemon reinstall, root grant revocation, force-stop, destructive transfer, remote writes, or release publication.

## Devtool improvements / follow-ups

- One four-node source-only Devtool DAG: contract guard → fixture negative tests → prior operations regressions → hosted-only Android build policy; Android compilation on GitHub remains independent.
- Add richer device receipt audit eventually: signed fixture manifest hash, observed run event sequence and terminal reconciliation hashes without leaking paths/credentials.
- Do not close all M3 simply from these gates: disposable `check` execution and cancellation are narrower than copy consent, durability and reboot recovery, cross-client BKX/chrootctl compatibility, and release acceptance.
