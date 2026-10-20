# Skybind M3 — single consolidated copy, replay, authority and consumer R0 source overlay

## Preserved qualification evidence (historical, not re-executed)

| Scope | GitHub run | Source SHA | Device evidence |
|---|---|---|---|
| M2-L1 read/browse | 39352843961 | c2cb64cdc3528c1de9814eb8ca4880b5aa778b8f | PASS historical |
| M2-L2 UI | 39363846767 | 6e36e46de1b28355296c5dd5367db98f7c4316d6 | PASS historical |
| M2-L3 negative | 39427946191 | 7cb78fde4b07d3b9d34e2e78b5f2839fc4626115 | PASS historical |
| M2-L3 transport and process | 39442535828 | def2d8722bb5b2c0419db259f291814a3ba723c9 | PASS historical |
| M3 real daemon preview (no run) | 39472233849 | af35406346680e2a813811127a88f07cee381053 | PASS historical |
| M3 disposable CHECK completion | 39491360742 / artifact 12296760416 | d00f222a79c117fb57909df6dc1d02fa60e574bc | PASS historical, exact local test-owned job |
| M3 session-owned cancel | 39491360742 / artifact 12296760416 | d00f222a79c117fb57909df6dc1d02fa60e574bc | PASS historical, independently selected lane |

The `false` fields in separately selected receipts do not negate historical PASS. None of the above proves whole-product release readiness.

## New implementation / safety contract

1. One isolated **COPY** definition, `M3DisposableCopy`, under the exact local media directory `Download/.skybind-m3-copy`. `interval_seconds=0` prevents scheduled runs. The helper **requires explicit `prepare --apply`**, and creates *source data only* plus a destination sentinel. Never prepopulate destination copies. No arbitrary CLI command, remote or host path is accepted.
2. The existing typed RootService issues a daemon proof-backed preview. New instrumentation checks exact fixed job/name/source/destination and one-use claim, disconnects, reconnects to a fresh app session, rejects the stale proof and foreign cancellation, then checks real terminal `COMPLETED` and replayed matching operation event. No arbitrary root shell or APK-initiated module install.
3. Authenticated exact GitHub APK-pair runner: the new `m3-copy-live` is opt-in only, requires **both** `--allow-disposable-job-execution` and `--allow-disposable-copy-writes` plus explicit test selection. No default mutation, no local Android builds. The runner independently verifies exact media file membership and deterministic SHA-256-based payloads *before and after* instrumentation. A protected destination sentinel must remain byte-identical; unexplained files, symlinks, changed data and incomplete transfers prevent PASS. One copy test does not qualify all copy destinations or provider behavior.
4. The existing app UI retains `job-copy-consent`, requiring a second explicit checkbox for destination writes. The instrumentation exercises the trusted broker, not the Compose consent UI; claim only the directly tested gate.
5. Guarded removal (`remove --apply`) requires verified final exact files and no active fixture run; it rejects unknown content and never recursively deletes. Failed/partial transfers may require separate **reviewed** recovery, not force-delete. Fixture paths are not user data storage.
6. CFS1 frozen 57-operation catalog is unchanged. The new R0 consumer matrix records the **current uploaded chrootctl October 20 files' SHA-256 as historical provenance only**, alongside CLI flags, executable/config constraints, and historical BKX requirements. Future consumer source hashes are never ABI or authorization pins. This is **not** functional R1/R2/R3/R4/R5/R6 compatibility: never expose Skybind credentials, share daemon root privileges, replace chrootctl's sealed executable, or redirect BKX's Restic repositories by default. Both consumers retain native rclone until independently authorized and device-tested.
7. Devtool composite DAG executes copy guard → pinned R0 consumer audit → negatives → existing M3 regression → cloud-only APK policy. GitHub source workflow runs the same new source checks. Distinct receipts must never be merged into blanket M3/release PASS.

## Operator sequence (Termux on emulator-5554)

After applying this **single** Devtool overlay to clean SHA `d00f222a79c117fb57909df6dc1d02fa60e574bc`:

```sh
./devtoolw m3-consolidated-source
git push origin main
gh workflow run skybind-android-apks.yml -R Mikeyphw/skybind --ref main
python3 -B scripts/dev/android/m3_copy_fixture.py prepare --apply --files 128
# Set RUN_ID to the NEW hosted build run; wait for GitHub Actions successful conclusion.
python3 -B scripts/devtool/ci_artifacts_device.py \
  --run-id "$RUN_ID" \
  --expected-sha "$(git rev-parse HEAD)" \
  --serial emulator-5554 \
  --install \
  --test m3-copy-live \
  --allow-disposable-job-execution \
  --allow-disposable-copy-writes
python3 -B scripts/dev/android/m3_copy_fixture.py verify
python3 -B scripts/dev/android/m3_copy_fixture.py remove --apply
```

**No hidden cleanup and no automatic repeat** if a result is ambiguous. The SHA binding of a new APK must be exact. `m3_copy_device_qualified=true` is reserved for full independently verified PASS. Real chrootctl root-module and BKX app-UID access remain BLOCKED/NOT_ATTESTED, as do daemon kill/reboot recovery, real remote cloud copy and all guarded sync/delete operations.

## Independent BKX/chrootctl updates — no repeated Skybind builds

This source overlay also installs `docs/contracts/rclone-compat/SKYBIND_CONSUMER_ABI_V1.json` and two example declarations, plus the independent R0 checker. Consumer source-hash drift by itself **must not** fail the ordinary compatibility gate or require rebuilding Skybind. Stable major-version/capability requests decide compatibility once the R1+ external gateway exists. A BKX or chrootctl update may update only its own adapter and run consumer-specific conformance; a new unsupported capability or changed Skybind ABI requires a **separately intentional** backend update. R1–R6 remain unimplemented/unqualified for external consumers; the native rclone fallback remains in both projects.

Sample source-only usage (does not build APKs or mutate the device):

```sh
python3 -B scripts/dev/android/m3_consumer_contract_gate.py \
  --consumer-declaration docs/contracts/rclone-compat/CHROOTCTL_CONSUMER_DECLARATION_EXAMPLE.json
python3 -B scripts/dev/android/m3_consumer_contract_gate.py \
  --consumer-declaration docs/contracts/rclone-compat/BKX_CONSUMER_DECLARATION_EXAMPLE.json
```

Both currently report external capabilities blocked. A new consumer version can supply its own declaration path; no Skybind source repin or Android APK rebuild is implied. See `docs/contracts/rclone-compat/INDEPENDENT_CONSUMER_UPDATE_CONTRACT.md`.
