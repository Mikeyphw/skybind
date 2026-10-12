# SB-Q07 — bounded boot recovery and meaningful reconciliation logs

**Prerequisite:** Working SB-R03 source with SB-Q06R2 supervisor observability already applied (the current installed baseline). This Devtool overlay deliberately refuses older/modified sources. **Do not reapply SB-R03 or Q06R2.**

## Changes

- A typed `ErrResourcePolicyDeferred` denotes a mount Start operation denied **before spawning any process** by existing resource policy checks. Such deferments do not consume the five real-start attempts; the next check is delayed by 30 seconds. The unchanged existing policy still fails closed when device facts are unavailable.
- Real start failures (FUSE, provider, identity, static runtime, missing paths) **still spend one attempt** and remain strictly bounded to five; the retry budget is persisted and does not automatically reset on an ongoing fault. Explicit stop is never remounted.
- Scheduled reconciliation writes only state changes, new attempts, or a heartbeat every 30 minutes. Backoff following policy deferral is coalesced. Recovery and reconcile-error resolution are logged as separate sanitized events. Hashed mount identifiers are used; credentials, raw provider errors and mount paths are never logged.
- Source-level regression tests cover continued policy block, later recovery, durable retry budget, exhausted real failures, explicit stop, error/redaction, deduplication and heartbeat.

## Apply to Termux checkout

Bundle ZIP contains `apply.sh` and the Devtool overlay. Place in `~/Downloads` then use the single command in the chat response. `apply.sh` verifies integrity and uses Devtool atomic apply with a clean worktree and strict source hashes; no `--keep-artifact`. On failure the download ZIP is retained if extracting succeeded, and Devtool's rollback should restore its source prestate.

Standalone overlay, when extracted from the bundle or downloaded separately:

```sh
cd "$HOME/Code/skybind"
devtool -r . --target skybind apply-overlay "$HOME/Downloads/SKYBIND_SB_Q07_BOOT_RELIABILITY_LOG_DEDUP.devtool-overlay.zip"
./devtoolw build-bclone
```

After the build, install the new candidate through your normal KernelSU workflow. The overlay itself does not touch the running module, perform any mount operation, reboot the device, or grant a release seal.

## Device qualification

The preexisting `skybind-qualify` Q06R2 monitor remains compatible. With a working mount, run `python3 ~/.local/bin/skybind-qualify run --cycles 0`, reboot normally, then run `python3 ~/.local/bin/skybind-qualify postboot --window-minutes 15 --poll-seconds 5 --stable-seconds 90`. Send the monitored postboot ZIP and a fresh Doctor Support ZIP, which includes audit transition events. If the mount was already running on the first poll, time to recovery is not measured by the monitor; supervisor transitions can narrow the window.

**Boundaries:** This change does not add unbounded automatic retry for FUSE or provider errors, change namespace/UID attestation, change process ownership requirements, or modify final release qualification (`NOT_ISSUED`). Physical Android boot/recovery is not certified by local tests.
