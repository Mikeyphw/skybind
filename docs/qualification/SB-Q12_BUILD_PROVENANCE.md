# SB-Q12 — Local source → candidate → installed module inventory

**Authority:** local inventory and hash correlation only. **Independent gates:** SB-G01…G08 remain governed by the original CFS1 verifier. **Final release seal: `NOT_ISSUED`.**

## Run

Apply SB-Q12 to a clean checkout that already contains Q11. On Termux:

```sh
cd ~/Code/skybind
./devtoolw q12
```

Output: `/storage/emulated/0/Download/skybind-q12-summary.json` and `skybind-q12-summary.md`. The command is read-only against the installed module. It asks root only to hash these fixed, public module payloads: `system/bin/skybind`, `system/bin/rclone`, `system/vendor/bin/fusermount3` and `runtime.provenance.json`. It does not read app configuration, remote data or credentials.

Candidate discovery is conservative. If zero candidates exist, the report says `NO_CANDIDATE`. If more than one local candidate exists, the report says `AMBIGUOUS_CANDIDATES_EXPLICIT_SELECTION_REQUIRED` and refuses to guess. To choose a candidate explicitly:

```sh
python3 scripts/dev/release/q12_provenance.py \
  --candidate /absolute/path/to/skybind-bclone-CANDIDATE-UNQUALIFIED.zip
```

Specify `--evidence-dir` and `--output-dir` only when collecting outside Android Downloads.

## Evidence semantics

- A candidate is valid only if the original `skybind_release.verify_release` accepts it. Hashes of four fixed installed members must match. `LOCAL_HASH_MATCH_NOT_ATTESTED` is **not** a signed device record.
- Q09 baseline is parsed through the checksum/schema/session checks of Q11. `RAW_HASH_MATCH_NOT_ATTESTED` is not independent device identification.
- Builds made **after this overlay** add `q12_source_build` to the adjacent `candidate-evidence.json` with actual Git commit/tree, clean status and candidate checksums captured at build time. This is strictly `LOCAL_SELF_REPORTED_ONLY`, not reproducibility or CI provenance. Incomplete/dirty source/build receipts fail closed.
- Previously built candidate archives have no SB-Q12 build-time record. Q12 **cannot retroactively prove** their source commit. Do not rebuild a working device module merely to silence an incomplete result.
- The original independent CFS1 verifier is executed verbatim and its gate results reported separately. Q12 never issues keys, signatures, independent receipts or final seals and never changes mount/FUSE policy.

## Still required

Independent signed G01–G08 receipts, separately trusted source/build/device chain, both provider reproducibility, real physical manager/negative security/Android namespace matrix, original WebView/browser/accessibility matrix, and externally issued final release seal.
