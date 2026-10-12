# SB-Q11 — Release evidence reconciliation (not certification)

SB-Q11 is a **non-privileged, read-only** Devtool job. It ingests existing Q09 archives from Android Downloads, verifies each archive's checksums and provenance *claims*, ensures one coherent session/build/mount identity, and derives stage results from actual observations rather than Q09's static release requirements.

Run after Q09 baseline, postboot, endurance, manual and app-probe:

```sh
cd ~/Code/skybind
./devtoolw q11
```

It produces `/storage/emulated/0/Download/skybind-q11-summary.json` and `skybind-q11-summary.md`. Termux requires shared storage access. For another evidence location or an explicitly chosen session:

```sh
python3 scripts/dev/release/q11_reconcile.py \
  --evidence-dir "$HOME/Downloads" \
  --output-dir "$HOME/Downloads" \
  --session 20261012T170516Z-a3a66e26
```

Optional `--candidate /path/to/candidate.zip` calculates that **local file's hash only**. It does not establish source-to-installed-module binding.

## Assurance boundaries

- Q09 evidence is **raw device evidence**; its SHA256SUMS does not authenticate the person/device that produced it.
- Q11 never changes or starts/stops mounts, modifies runtime inputs, installs the module, signs attestations, or issues gate passes.
- A successful app UID test is recorded as `RAW_DEVICE_PASS`, not independent G08 approval. Manual reports remain `USER_REPORTED_PASS`.
- CFS1 remains the **authoritative independent gate evaluator**. It reads externally pinned signatures/run receipts only through its documented `SKYBIND_*` trust inputs. Q11 simply reports CFS1's actual statuses and does not fabricate external evidence.
- A source commit, local build hash or ZIP fingerprint alone does not bind the installed module to a reproducible external release candidate. The G01–G08 suite, negative security matrix, both upstream provider builds, original WebUI parity, manager/device matrix and independent final seal still require their original assessments.
- Any invalid ZIP inside the explicitly selected Q09 session aborts the reconciliation rather than being silently skipped. Sample/fixture sessions must not be mixed with real evidence.

`NOT_ISSUED` is the expected release seal until externally issued evidence satisfies all existing source-bound conditions. See `docs/gates/SB-CFS1_FINAL_SEAL_CONTRACT.md` and `docs/gates/SB-CG1_GATE_EVIDENCE_CONTRACT.md`.
