# Skybind SB-Q15 — Independent G01/G02 Evidence Readiness

SB-Q15 is a **read-only bridge and audit**, not a source-build gate receipt producer. It never changes `sb_g01.py`, `sb_g02.py`, `sb_cfs1.py`, `build/evidence`, FUSE, module contents, or the user's installed Skybind. CFS1 remains authoritative.

## What it does

1. Re-reads `skybind-q14-summary.json` only as a **lead**. It does not trust the report's `private_ci_signatures_verified` flag by itself.
2. Re-reads both original candidate lanes from the local Q14 Downloads directory. Checks that the exact file set is present (neither extra nor symlinked), the original ZIP members pass the Q12/Q13 candidate verifier, the source commit and both provider digests match the build receipts and Q14 summary, A/B builds are byte-identical and shared Skybind/FUSE payloads match.
3. **Reverifies** each lane's Ed25519 manifest against a public key pinned outside the repo and downloaded artifact directory. Optionally re-queries the authenticated GitHub run API with `--reauthenticate-github`.
4. Calls **unchanged** original `sb_g01.evaluate`, `sb_g02.evaluate`, and `sb_cfs1.evaluate`. Reports exact required G01 and G02 evidence fields: `source.lock.json`, real provider build archives, original overlay IDs, G02 source SHA-256, independent Devtool negative-test obligations and fixed-point runs.
5. Writes `skybind-q15-summary.json` and `.md` to Android Downloads. If the expected evidence files are missing, produces a **blocked** report and nonzero exit rather than promoting any missing tests.

## Run on Termux

```
cd ~/Code/skybind
./devtoolw q15
```

This uses the existing run `38336604093` by default. For new runs or different input paths:

```
python3 scripts/dev/release/q15_gate_bridge.py \
  --q14-report /storage/emulated/0/Download/skybind-q14-summary.json \
  --artifact-root /storage/emulated/0/Download/skybind-q14-run-38336604093 \
  --trusted-public-key "$HOME/.config/skybind/trust/q14-ci-public.pem" \
  --reauthenticate-github \
  --output-dir /storage/emulated/0/Download
```

Run `gh auth status` first if requesting fresh GitHub API reauthentication. If Q14's preserved lane directory was moved or deleted, rerun Q14 to fetch the original GitHub artifacts into a new directory. **Never import only the JSON report as cryptographic evidence.**

## Original gate contracts (not replaced)

**SB-G01** reads `build/evidence/sb_g01_provider_builds.json`. The exact evaluator requires `qualification=REAL_PINNED_PROVIDER_BUILD`, a SHA256 match to `scripts/dev/runtime/source.lock.json`, closure for SB-O01–SB-O05, two verifiable clean independently qualified provider builds per provider, consistent source commit and helper parity. The maintainer-controlled Q14 Ed25519 signature cannot establish externally verified official-source provenance. Q15 will not fill `verified_official_source=true` or create that file.

**SB-G02** reads `build/evidence/sb_g02_source.json`. The exact evaluator depends on G01, a pinned source commit and hashes over nine source files, SB-O01–SB-O09 closure, two distinct clean fresh Devtool validation runs with on-disk raw run-store evidence, and all ten negative security checks. Q14 candidate builds alone do not provide those runs. Q15 will not create fabricated receipts or write that file.

## Assurance boundary

`OWNER_SIGNED_CANDIDATES_REVERIFIED_NOT_INDEPENDENT` means the exact downloaded CI bytes and their signatures were rechecked using the **owner-pinned** key. It does not imply a different signing authority, independently run provider builds, independent Devtool run custody, or G01/G02 qualification. Repo-admin Actions secrets cannot substitute for an independent attestation. No CFS1 gate promotion. Final release remains `NOT_ISSUED`.
