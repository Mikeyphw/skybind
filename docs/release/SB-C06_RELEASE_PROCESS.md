# SB-C06 — deterministic candidate and release-truth boundary

`scripts/dev/release/skybind_release.py` accepts only a separately SHA-verified
build-time provider ZIP and the Android/arm64 Skybind native ELF. It combines
those files with source-controlled Android module hooks and the original Skybind
WebUI, using fixed timestamps/order/modes and SHA-256 manifest + SHA256SUMS.

A produced module is labeled `CANDIDATE_ONLY_NOT_SEALED`. The verifier rejects
payload mutation, archive traversal/symlinks, wrong architecture, changed modes,
missing UI assets or release claims. A missing NewFuture archive hash or bclone
pin blocks production runtime creation. Synthetic ELF fixture packages used by
unit tests are not upstream binaries and never qualify.

The source-only SB-C06 Devtool workflow exercises deterministic rebuilding,
manifest verification, deliberately corrupted archives, lock preconditions,
original DOM/source contracts, secret leak sentinels and source regressions.
Android device checks are separate Devtool target workflows and must run on
physical hardware with ordinary-app access evidence. Final gate definitions
and seal belong to `SB-CG1` and `SB-CFS1`, not SB-C06.

Do not publish/install candidate artifacts as verified releases without
independent G01–G08 and final evidence. No dynamic runtime, update or migration
facilities are part of Skybind.
