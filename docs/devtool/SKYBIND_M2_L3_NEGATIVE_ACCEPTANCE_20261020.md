# M2-L3 read-only negative acceptance — first safe sublane

**Source baseline:** GitHub `Mikeyphw/skybind` main `6e36e46de1b28355296c5dd5367db98f7c4316d6` (M2-L2 PASS). This change is not itself a device PASS.

## Implemented (additive)

- Guard superseded RootService binding callbacks from invalidating a later authenticated session. Retire the old connection pointer before app-owned unbind; no daemon shutdown.
- Explicit `m2-negative-live` sublane invokes exactly one AndroidTest method via the canonical signed GitHub APK runner.
- Check pre-connect `NOT_AUTHORIZED`, no remotes/jobs/events/cursor; a real explicitly initiated RootService bind; local rejection of traversal and malformed remote syntax; no loss of the still valid read session; and complete read-only session teardown.
- Denied/unavailable real grant, unavailable daemon and no remote are `BLOCKED`, not success. Negative assertion regressions are `FAILED`. Narrow pass = `PASS_M2_L3_READONLY_NEGATIVE_BOUNDARIES` with `m2_l3_negative_device_qualified=true` and `device_qualified=false`.
- Source-only two-node Devtool DAG `m2-negative-source` and Python regressions protect the assertions and receipt identity. GitHub APKs are built only by `.github/workflows/skybind-android-apks.yml`.

## Execution / qualification

1. Apply the source-bound Devtool overlay on clean `main`, then push resulting auto-commit.
2. `./devtoolw m2-negative-source` for source-only DAG (or use `devtool` workflow).
3. `gh workflow run skybind-android-apks.yml -R Mikeyphw/skybind --ref main` and wait for successful **new** run. Hosted AndroidTest compilation is mandatory; never claim it from Python checks.
4. `python3 -B scripts/devtool/ci_artifacts_device.py --list-tests` and verify `m2-negative-live` present.
5. `python3 -B scripts/devtool/ci_artifacts_device.py --run-id <NEW_GITHUB_RUN_ID> --expected-sha "$(git rev-parse HEAD)" --serial emulator-5554 --install --test m2-negative-live`. `--install` explicitly permits only same-signer upgrade, never removal or data clearing; omit if installed pair already matches.
6. Inspect `summary.json` and individual lane receipt. Keep originals unchanged. A PASS qualifies **only** the read-only negative boundaries; older M2-L1/L2 receipts remain authoritative for their own SHAs.

## Open M2-L3 gates

- KernelSU root-grant denial/revocation: no automatic consent changes; operator/test-specific opt-in and independent evidence required.
- Non-disruptive *unexpected* transport failure: stronger binder-loss and stale-completion concurrency tests beyond the guarded late-callback source fix.
- Test app process force-stop/cold launch: independent optional external coordinator, explicit authorization and source-/pair-attested receipts. Never conflate Activity recreation from M2-L2 with process death.
- Real daemon death/restart: NO default daemon stop. Independent authorization and recovery plan required.
- Negative UI semantics for unsupported daemon version, remote disappearance, event cursor gaps and narrow layouts; separate reviewable lanes.
- Broad release, BKX/chrootctl R0–R6, A4–E API requirements remain governed by unified API roadmap.
