# Skybind M3 consolidated daemon registry recovery and snapshot diagnostics — 2026-10-20

## Evidence and source-bound starting point

- Source preimage: `296141ac01f2b0716b52d16169bae0f0de2b3e27` (M3 operations hosted Android build GitHub run `39465999694`, authenticated artifact `12284827401`).
- On-device `m3-preview-live` receipt: `BLOCKED`, `SKYBIND_M3_BLOCKED_DAEMON`; no M3 preview execution or qualification. Installed exact APK pair was verified.
- Same-device Termux privileged CLI health check: `system.capabilities` protocol 1, all 57 operations; `runtime.status` object; 12 configured `provider.remotes`; empty `mount.list`; `operation.events` object/cursor 0; `jobs.status` object, `runs` array, but `registry.jobs` was **not an array**. These facts were reported by the user and are not a new device test or promoted attestation.
- ADB `emulator-5554` shell has no `su` executable; that alone does not contradict the Termux root-service/daemon health. Do not restart, reset, or reinstall root-manager/daemon based on this output.

## Consolidated root cause and remediation

1. **Go producer:** `internal/jobs/jobs.go` had `clone()` using `append([]Job(nil), r.Jobs...)`. For zero jobs it returns a **nil** slice and marshals it as `null`, even when initial `Empty().Jobs` was allocated as `[]`. `jobs.status` and `jobs.snapshot` both return clones. The producer now copies into a non-nil `[]Job{}` so empty jobs serialize `[]` and ownership isolation remains intact. New Go regressions cover both RPC shapes and copy isolation.
2. **Android consumer:** `LiveReadSnapshotReader` accepts `registry.jobs:null` *only when that field is explicitly present* and `registry.schema_version=1` with a nonnegative revision; it interprets this historical zero-jobs serialization as empty. Missing fields, invalid shapes, bad schemas/revisions, oversize arrays and unknown job types are still rejected. Legacy compatibility does not grant preview/run authority or start jobs.
3. **Diagnostics:** Snapshot failures now identify a fixed allowlisted stage such as `jobs.status`, without exposing paths, remote names, responses, error text or credentials. The M3 instrumentation classifies `API_MISMATCH`, `ROOT_AUTH`, `JOBS_STATUS` and generic daemon blockers independently in the fail-closed runner. Invalid data remains BLOCKED, never PASS.
4. **Tests/DAG:** Kotlin regression fixtures test explicit null versus absent/bad registry; independent M3 Go and Python security contracts are integrated with a four-node Devtool DAG and its ordinary hosted-build policy. The full M1/M2 source gates remain part of overlay validation.

## Mandatory qualification boundaries

- This overlay fixes source and adds assertions only. The existing daemon binary **is not replaced** by the GitHub Android APK workflow. The Android compatibility reader works with the existing nullable producer; a later separately qualified daemon/module package is needed to deploy the Go producer fix.
- The M3 preview lane remains read-only and opt-in. After the new APK pair is authenticated/installed, an *empty* job registry should result in `SKYBIND_M3_BLOCKED_NO_ELIGIBLE_JOB`, not PASS. A `check` or `copy` job must be configured and enabled by the user through existing authenticated daemon management before the preview can be qualified. This overlay does **not** create a fixture or start/cancel a job.
- Destructive sync stays locked; proof/confirmation/ownership guards stay unchanged. Write-capable or disposable job execution, root-grant revocation, daemon process death, BKX/chrootctl native rclone surface, and release qualification remain separate obligations.
- Previous M2-L1, M2-L2, M2-L3 negative/transport/cold-launch PASS receipts remain historical evidence; none is rerun or implicitly promoted.

## Next commands after applying source-bound overlay

```sh
cd ~/Code/skybind
./devtoolw m3-operations-source
git push origin main
gh workflow run skybind-android-apks.yml -R Mikeyphw/skybind --ref main
```

Only after the *new* GitHub run succeeds, set `RUN_ID` to that run ID and run:

```sh
python3 -B scripts/devtool/ci_artifacts_device.py \
  --run-id "$RUN_ID" \
  --expected-sha "$(git rev-parse HEAD)" \
  --serial emulator-5554 \
  --install \
  --test m3-preview-live
```

A current on-device no-job blocker does not warrant another micro-overlay. Next consolidated development package should include an explicitly approved disposable fixture lifecycle and controlled real run/cancel qualification, followed by roadmap M4 when the independent gates are complete.
