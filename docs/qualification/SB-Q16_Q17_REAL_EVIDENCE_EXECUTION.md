# SB-Q16 + SB-Q17 — original provider and Devtool evidence collection

Scope: real evidence execution; **never gate promotion**. This single change modifies CI artifact retention and adds local evidence collectors. The production module, FUSE implementation, Q14 private signing, `sb_g01.py`, `sb_g02.py`, and `sb_cfs1.py` remain untouched.

## Q16 — two real upstream provider builds

The existing `skybind-provider-reproducibility.yml` already runs two separate fresh Ubuntu jobs pinned to the original Q02 source-lock. Q16 additionally preserves the NewFuture **original release asset** and a self-contained Git bundle of the **exact pinned bclone commit and its reachable history** in each job artifact (not just a repackaged Q14 candidate). No keys are packaged.

1. Apply overlay, then `git push` the commit containing the upgraded workflow.
2. Trigger `gh workflow run skybind-provider-reproducibility.yml --ref main`.
3. Wait: `gh run watch <RUN_ID> --interval 5 --exit-status`.
4. Verify/download the actual original bytes: `python3 scripts/dev/release/q16_provider_evidence.py --run-id <RUN_ID> --repo Mikeyphw/skybind --output-dir /storage/emulated/0/Download`.
5. Send `skybind-q16-summary.json` and the full `skybind-q16-run-<RUN_ID>` directory as a ZIP to a separate authorized reviewer. The CI artifact files remain raw evidence. **Original upstream origin and independent builder custody require additional independent verification**; this tool never writes `build/evidence/sb_g01_provider_builds.json`.

Q16 verifies source.lock.json, GitHub run identity/status/commit, two distinct successful lane jobs, original NewFuture asset SHA-256, bundled bclone Git commit object, arm64 builds via original Q02 verifier, both provider package archives, helper parity and A↔B byte identity. On any mismatch it fails closed. GitHub API identity is distinct from independent origin attestation.

## Q17 — fresh Devtool negative runs

After pushing and ensuring `git status --porcelain` is empty, run `./devtoolw q17` **twice as separate Devtool executions**. Each starts ten real `go test -json -count=1` subprocesses with exact names and records per-case logs, source commit/tree and all nine G02 source hashes in `/storage/emulated/0/Download/skybind-q17-runs/q17-run-<uuid>/`.

Compare the actual receipts/logs with:

```sh
python3 scripts/dev/release/q17_fixedpoint_runs.py compare \
  --first /storage/emulated/0/Download/skybind-q17-runs/q17-run-<FIRST> \
  --second /storage/emulated/0/Download/skybind-q17-runs/q17-run-<SECOND>
```

Q17 checks unique executions, complete logs, negative-test PASS events, commit and source-hash identity. But the receipt **does not authenticate the Devtool run ID, zero-warning external audit, isolation, independent custody, or full fixed-point behavior**. Those remain review obligations. No `build/evidence/sb_g02_source.json` is generated.

## Acceptance boundaries

- `SB-G01` requires separately vetted and independently authenticated original upstream source/builds; a GitHub run is not an independent reviewer.
- `SB-G02` requires separately validated Devtool fixed-point results and ten negative cases with authentic receipt identities; a local test runner is not independent attestation.
- CFS1 retains all eight original gates, with `NOT_ISSUED` until a separately trusted evaluator accepts proper gate evidence.
- Q16 and Q17 cannot be used to replace G01/G02 with self-asserted `verified_official_source`, fabricated `fresh_devtool_runs`, or a maintainer-controlled signature.
