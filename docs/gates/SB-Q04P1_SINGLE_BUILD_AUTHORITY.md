# SB-Q04P1 — Exact verified build artifact packaging (source contract only)

**No real provider CI jobs or Android devices executed in this overlay. All gates G01–G08 remain BLOCKED, final seal NOT_ISSUED.**

## Defect corrected

The SB-Q02 independent CI lane originally built bclone into `dist/lane/bclone_build` and then invoked `skybind_runtime.py package --bclone-checkout`, which compiled a *second* copy. The comparison phase rejected different bytes, but correct first-build bytes were not guaranteed to be the actual input to the packager; this caused unnecessary build duration and additional nondeterminism.

The lane now packages with `--bclone-build-dir dist/lane/bclone_build`. The packager verifies `rclone`, `SHA256SUMS`, canonical `provenance.json`, source commit, exact source.lock SHA-256, selected NDK and Go versions, ELF64/AArch64 format and the binary size/digest before consuming exactly those bytes. It rejects missing/malformed receipts, symlinks and ambiguous simultaneous rebuild inputs. The independent comparison continues to match each packaged bclone runtime to its lane's verified build output and compare full provider ZIP hashes across lanes.

Local `--bclone-checkout` packaging stays supported for offline source workflows, but CI never recompiles during packaging.

## Genuine G01 prerequisites remain

* Independently approved NewFuture artifact custody despite `vcs.modified=true` and mutable release metadata.
* Independently reviewed bclone Git commit and dependency graph (unsigned commit noted).
* Authenticated Go 1.27.2 and NDK 28.2.13676358 inputs and explicit source-lock sign-off.
* Two real clean CI jobs with trustworthy receipts, comparison and independent signature review.
* Android device/FUSE/ordinary-app qualification and separate release signature/seal.

`source.lock.json` remains unchanged and null. Devtool and GitHub source-contract tests do not assert real provider builds or release promotion.
