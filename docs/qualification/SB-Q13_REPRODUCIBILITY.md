# SB-Q13 — Cross-provider reproducibility and gate blocker inventory

This is a **local, read-only evidence preparation tool**. It never downloads
untrusted provider binaries, builds an APK, mounts FUSE, signs a receipt, changes
trust pins, updates release gates, or issues the external final seal.

## Providers and expected differences

The two configured runtime providers are `newfuture` and `bclone`. The
`system/bin/rclone` ELF differs **by design** between providers. Comparing
newfuture to bclone as if their provider binaries should be identical is wrong.

Two logically separate tests are required:

- **Same-provider repeat-build comparison**: independently run lane A and lane
  B must each produce an unqualified candidate ZIP for *each* provider.
  Q13 calls the existing canonical Q05 release verifier for every candidate,
  validates its build receipt/hash, then compares the A/B ZIP bytes by SHA-256.
  A byte match is `BYTE_IDENTICAL_UNATTESTED`, not proof of builder isolation.
- **Cross-provider shared payload comparison**: within each lane, Q13 checks
  byte hashes for the Skybind daemon and NewFuture FUSE helper. Runtime provider
  ELF and provider provenance are expected to be different. Full original WebUI
  and payload manifests remain checked by the existing candidate verifier.

Q13 also optionally checks the original Q04 pinned provider evidence using
`q05_candidate.evidence_inventory`, then runs the **unchanged** G01–G08 and
CFS1 evaluators to collect their actual blocker reasons.

## Termux commands

After applying the overlay:

```sh
cd ~/Code/skybind
./devtoolw q13
```

This inventories exactly one existing `candidate-*` directory if available.
With multiple directories, explicit selection is mandatory, not newest-first.
With no candidate available, Q13 still reports original release blockers.

For separately executed repeat builds, run the new manual GitHub Actions workflow
`.github/workflows/skybind-q13-candidate-reproducibility.yml`. Its A and B
jobs are isolated runners, and the comparison job fails if either provider differs.
These CI outputs remain raw, **unattested** evidence, not verified independence
or signed G01 proof. The workflow requires the original pinned Q04 artifacts
to remain available; expiration fails closed.

You can also produce both `newfuture` and `bclone`
from two separate clean environments (such as two distinct pinned CI runners).
A local build can be created with `./devtoolw build-both` but **two runs in
one shell do not constitute independent CI attestation**. Transfer their
`candidate-*` directories and verified raw runner receipts to an isolated
comparison environment. Compare without installing either candidate:

```sh
python3 scripts/dev/release/q13_reproducibility.py \
  --lane-a /absolute/path/to/lane-a/candidate-... \
  --lane-b /absolute/path/to/lane-b/candidate-... \
  --output-dir /storage/emulated/0/Download
```

Use `--q04-evidence-root /absolute/path` to verify an explicitly selected Q04
upstream evidence root. Outputs are `skybind-q13-summary.json` and `.md`.

## Gate interpretation

Q13 shows per-gate *actual evaluator* reasons from `sb_g01.py`, `sb_g02.py`,
`sb_cg1.py` and the original `sb_cfs1.py`. It does **not** write into any gate
trusted evidence directory or manufacture receipt metadata. For release
qualification, an independent custodian must establish real source/authorship,
two distinct build run receipts, physical manager and negative-test results,
WebView/browser/accessibility testing and pinned external signature trust.

Without those verified independent steps, all relevant gates stay `BLOCKED`
and the final seal stays `NOT_ISSUED`, even if local ZIP bytes match.
