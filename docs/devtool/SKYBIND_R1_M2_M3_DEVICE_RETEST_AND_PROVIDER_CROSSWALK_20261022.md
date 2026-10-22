# Skybind R1 — fresh M2/M3 device retests and independent-provider readiness (2026-10-22)

**Status: SOURCE IMPLEMENTED, LOCAL REGRESSIONS PASS. FRESH DEVICE RETESTS NOT YET RUN; EXTERNAL PROVIDER/RELEASE NOT QUALIFIED.**

This consolidates two adjacent handoff windows: (1) preserve the already-committed BKX empty-path coordinator handshake fix after 12/12 live socket PASS; (2) obtain a *fresh*, one-admission automated M2/M3 Android device batch and reconcile it with the earlier 21-case R1 security pass without self-attesting release or provider custody.

## Preserved passed evidence

- BKX live Android instrumentation `acceptance-bkx GDDavys ssd`: 12/12 PASS, attested kernel peer, JUnit terminal pass, separate-process token replay denied. Root-private receipt `/data/adb/skybind/r1-bkx-acceptance/r1-bkx-969c677654209b852bb0e734ec7c9a77.json`.
- chroot-ctl earlier independent security run: nine cases PASS.
- R1 consolidated Termux receipt `~/.local/state/skybind/r1-final-report/r1-bkx-consolidated-3bf26ab28a7046208c91050b13afd3f2.json`, `PASS_R1_BKX_AND_CHROOTCTL_NARROW_LIVE_ACCEPTANCE_ONLY`.
- These receipts are unchanged; they **do not** establish M2/M3 fresh retests, external provider custody, G01 or release qualification.

## New implementation and proof bounds

1. `scripts/dev/android/m2_m3_retest_batch.py` executes a fixed ordered test catalog, with a **single** hosted source/signature validation, installed APK-pair byte validation, device API/SELinux preflight, and one immutable 0600 batch receipt. It never installs/uninstalls APKs, clears data, prepares/removes fixtures or changes root grants.
2. Default `--profile readonly` executes **five** cases: M2 L1 browse/rebind; M2 L2 real Compose UI recovery; M2 L3 negative read boundaries; M2 L3 transport recovery; M3 read-only job preview. An explicit `--remote GDDavys` constrains remote selection.
3. Explicit `--profile full` executes **nine** cases: those five plus opt-in test-owned CHECK completion, owned cancellation, local fixture COPY with SHA-256 and sentinel verification, then Skybind **app-only** force-stop/cold-launch UI observation. Four independent flags are mandatory: `--allow-disposable-job-execution`, `--allow-disposable-job-cancellation`, `--allow-disposable-copy-writes`, `--allow-app-force-stop`. There is no arbitrary job name, shell command, remote transfer or app/daemon uninstall. The force-stop is **only the Android Skybind app**, never the daemon or BKX. Disposable fixtures must be explicitly prepared and reviewed beforehand; no implicit mutation or cleanup.
4. Each lane consumes the canonical existing M2/M3 terminal parser. A failed, skipped, contradictory, timed-out or process-exit-nonzero instrumentation is never PASS, even if Android prints `INSTRUMENTATION_CODE: -1`. The first unsuccessful lane stops the batch; the saved receipt names the exact blocked lane without persisting sensitive full instrumentation stdout.
5. New `m2_m3_device_retests_run=true` only after **all nine fresh cases** PASS in one fully consented run. The five-lane read-only receipt can pass its own narrower scope but leaves that flag false. Prior historical M2/M3 results are preserved and never relabeled as fresh runs.
6. Fix existing `m2_live_device.py` CLI: it had an implemented `m3-copy-live` case in `run()` but omitted it from `choices` and never exposed the required `--allow-disposable-copy-writes` authorization flag. Both are now reachable, fail closed.
7. Preserve the already-fixed R1 coordinator's `bkxReply.Path` `json:"path,omitempty"`: the BKX Kotlin test calls `hello.getString("path")` and crashed when an authorized empty relative path was omitted. Existing source fa608eb emits explicit `"path":""` and regression-tests empty/nonempty cases; this patch leaves that fix unchanged. The already passing `ssd` security receipt **does not** need rerunning. Existing policy/certificate remain untouched.
8. `scripts/dev/qualification/r1_remaining_gates.py` validates the *shape and exact case set* of the supplied 21-case R1 evidence and optional fresh M2/M3 and Q16 summaries, references their SHA-256 digests, emits root/private-compatible immutable 0600 status, and **always** leaves `external_provider_qualified=false`, `release_qualified=false` and G01 independent-review state pending. This is a sourced crosswalk, not independent source custody or a release seal.
9. Q16 remains the existing workflow and evidence collector: two real fresh NewFuture/bclone provider-build lanes and source-lock checks provide **raw reproducibility evidence**, not independently authenticated original publisher, independent builder custody or release. An actual independent G01 reviewer and original CFS1 gates are still necessary.

## One-pass operator workflow (Termux; no manual case-by-case commands)

First apply this source-bound Devtool overlay on top of fa608eb, push the new Skybind commit, and invoke **hosted-only** Skybind Android APK compilation:

```sh
cd ~/Code/skybind
./devtoolw m3-consolidated-source  # optional source suite
# the overlay's own validate.sh already executes focused tests

git push origin main
gh workflow run skybind-android-apks.yml -R Mikeyphw/skybind --ref main
# use the successful exact-SHA workflow_dispatch RUN_ID returned by gh run list
RUN_ID=REPLACE_WITH_APPROVED_SUCCESSFUL_RUN_ID
```

Use the existing already-audited exact-hosted-pair installer; it requires explicit opt-in and rejects mismatched installed signing identities. Neither runner itself mutates APK state:

```sh
python3 scripts/devtool/ci_artifacts_device.py \
  --run-id "$RUN_ID" --expected-sha "$(git rev-parse HEAD)" --install \
  --remote GDDavys
# With the exact hosted and installed pair matching, the new batch consumes that cached pair.
python3 scripts/dev/android/m2_m3_retest_batch.py \
  --run-id "$RUN_ID" --remote GDDavys --profile readonly
```

For the full nine-lane workload only after separately preparing the **bounded local fixtures** and deciding to authorize device mutation:

```sh
python3 -B scripts/dev/android/m3_disposable_fixture.py prepare --apply
python3 -B scripts/dev/android/m3_copy_fixture.py prepare --apply --files 128
python3 -B scripts/dev/android/m2_m3_retest_batch.py \
  --run-id "$RUN_ID" --remote GDDavys --profile full \
  --allow-disposable-job-execution \
  --allow-disposable-job-cancellation \
  --allow-disposable-copy-writes \
  --allow-app-force-stop
```

**No automatic cleanup.** The M3 COPY fixture must remain intact for post-verification. Remove the exact owned fixtures *only after reviewed successful verification* with the already provided explicit `remove --apply` routines. Failure requires inspecting receipt/fixture first; do not delete or rebuild unrelated user data. If ADB is not connected, the batch blocks without modifying the device. For multiple ADB devices pass `--serial` to the commands.

To reconcile the passing R1 receipt with the newest fresh nine-case device receipt, use its exact printed `receipt` path:

```sh
python3 -B scripts/dev/qualification/r1_remaining_gates.py \
  --r1-receipt "$HOME/.local/state/skybind/r1-final-report/r1-bkx-consolidated-3bf26ab28a7046208c91050b13afd3f2.json" \
  --m2-m3-receipt "$HOME/.local/state/skybind/m2-m3-retests/REPLACE_WITH_FRESH_RECEIPT.json" \
  --remote GDDavys
```

Provider work after this: dispatch the **separate** `skybind-provider-reproducibility.yml` successful workflow on an approved source and run `python3 scripts/dev/release/q16_provider_evidence.py --run-id <Q16_RUN_ID> --output-dir <NEW_REVIEW_DIRECTORY>`; preserve both raw lane artifacts, source lock and independent reviewer trace. The crosswalk accepts the Q16 summary as *reviewable raw evidence only*, not authoritative origin/custody qualification.

## Acceptance and failure audit

| Promise | Source implementation | Real device qualification |
|---|---|---|
| Existing BKX 12/12 and chrootctl 9/9 evidence preserved | Delivered, no modifications | Previously PASS by independent receipts |
| Empty-path BKX hello key always sent | Previously committed fa608eb, existing Go regression | Existing nonempty path 12/12 still PASS; empty-path variant not rerun |
| M2 L1/L2/L3 five read-only scopes | Implemented single-admission batch | Pending new hosted APK/current-installed pair and device receipt |
| M3 disposable CHECK/cancel/COPY with SHA256/sentinel | Implemented, explicit test-owned-only flags and fixture preflight | Pending fresh opt-in device receipt |
| M2 app-only process cold-launch | Implemented, separate explicit force-stop opt-in | Pending fresh device receipt |
| Aggregate flags truthful when any one lane blocks | Python regression checks | Pending device evidence |
| Q16 two upstream builder lanes | Existing collector preserved | Raw evidence / independent provenance not established here |
| Independent G01 external provider and production release | Never self-authorized | Open / false |

This work avoids Android APK compilation in Termux; only GitHub hosted workflow produces installable Skybind APKs. No R1 policy rotation, root credential export, forced uninstall or hidden B/K consumer mutation is performed by this overlay.
