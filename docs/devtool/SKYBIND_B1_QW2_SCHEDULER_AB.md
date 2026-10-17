# B1-QW2 — Native-Termux scheduler A/B qualification harness

This source-bound Devtool overlay builds on **applied B1-QW1**. It adds an opt-in witness for the existing `skybind_release#r1-full-regression` workflow. It **does not change** the default scheduler, run Go tests during overlay installation, or enable any Android / broker runtime.

## Staged native usage

From a **clean, committed** Termux checkout after installing the overlay:

```sh
cd ~/Code/skybind
python3 scripts/dev/qualification/r1_scheduler_ab.py plan
# Choose a unique id for this A/B run, for example b1-qw2-001.
python3 scripts/dev/qualification/r1_scheduler_ab.py baseline --campaign b1-qw2-001
python3 scripts/dev/qualification/r1_scheduler_ab.py candidate --campaign b1-qw2-001
python3 scripts/dev/qualification/r1_scheduler_ab.py compare --campaign b1-qw2-001
```

Each stage is independently requested. **Candidate is blocked until the baseline passes.** If a run fails or is interrupted, its own stage directory is retained and no automatic retry or source-pass promotion occurs. Use a **new campaign ID** after investigating a failure; earlier evidence remains untouched. Progress comes from Devtool logs, but the harness does not suppress Devtool failures. Plan is non-executing.

## Scope of validation

- Uses `devtool plan` to check actual eight source-gate jobs, write scopes, exclusive Go reservation, and at most **one Go job per scheduling wave**.
- Baseline invokes Devtool with `--no-workflow-parallel`. Candidate explicitly uses `--workflow-parallel --workflow-max-workers 3`. Scheduler defaults are untouched.
- Requires Devtool machine envelope to pass **all eight real job results**. Witness captures raw Devtool log bytes, machine envelope, hashes, local duration, plan evidence and original Go receipt.
- Independently revalidates every Go package log digest, package count, full selection, source digest, source Git HEAD, `complete`, `qualified`, WaitDelay and timeout flags.
- `compare` validates identical Git/config identities and package inventories, both unmodified summary receipts and their log files. It reports observed wall-clock difference once, not a general performance guarantee.
- New evidence: `build/evidence/r1-scheduler-ab/<campaign>/...`; original Go receipts remain in `build/evidence/go-regression-isolated/`.

This qualifies **source-only R1 scheduler execution**, not APKs, CI, device behavior, broker listener authorization or final release. Do not infer performance gains from planner wave count alone. The GitHub Actions APK pipeline and trusted Android identity bridge remain separate subsequent work.
