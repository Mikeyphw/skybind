# SB-Q03R1 — Trust-pin review and Go security alignment

**No pin approved / no upstream binary attested / G01–G08 BLOCKED / final seal NOT_ISSUED.**

Review of user-provided GitHub Actions run `38099529777` identified an internally consistent NewFuture asset with SHA-256 `04ebfcc8c21c9583b7d4c723e2e69c1d3bbbd24432f6728ffbc2947e5282aa43`, and the full bclone candidate `7b63b1a4cc9d13465721ebbfc96f2f9bd810f600`. Neither candidate is automatically entered into `source.lock.json`.

## Explicit engineering toolchain choice

The future **bclone** source build is moved from Go 1.27.1 to **Go 1.27.2** in `source_build.py` and its independent-lanes GitHub workflow because [Go's official release history](https://go.dev/doc/devel/release) documents security fixes in 1.27.2 (2026-10-08). Android NDK `28.2.13676358` and Android API 21 are retained. This is a *build policy update*, not an authenticated toolchain-package digest or approval of a third-party binary.

The existing **NewFuture** release binary identifies itself as built with Go 1.26.5, Android NDK r27d and `vcs.modified=true`; it is **not** rebuilt by merely changing Skybind's bclone Go pin. Its ZIP was not immutable at the time of metadata collection. These findings need an upstream explanation, a signed release attestation, or a separately verified/rebuilt source pipeline before a reviewer can accept its custody risk.

The bclone GitHub API claims `verification.verified=false`, reason `unsigned`. Exact commit/parent, dependency graph, Git object bytes, upstream ownership and package pinning require independent review and explicit approval.

## Replay the user's saved evidence

After extracting the original, **user-provided** `sb-q03-evidence-38099529777.tar.gz` into a private directory, locate the inner folder `sb-q03-raw-upstream-review` that contains `inputs/` and `outputs/`, then run:

```sh
python3 scripts/dev/runtime/pin_review.py \
  --evidence-dir /private/path/sb-q03-raw-upstream-review \
  --output /private/path/sb-q03r1-review.json
```

It verifies every SHA256SUMS entry; the exact candidate archive, asset ID, release JSON and GitHub commit JSON; ZIP member paths/ELF architecture; recorded bclone Git parent; and raw evidence report consistency. It rejects tampering, missing files, symlinks, duplicated ZIP members, a previously changed `source.lock.json`, and writes its output only to a **new** file outside the checkout with mode `0600`. This is still merely reconciliation of the same uploaded runner evidence, **NOT independently authenticated custody**. Do not commit downloaded binaries or claim this report as cryptographic attestation.

## Open blockers / authorization required

1. Authenticate NewFuture artifact authorship/custody independently; request exact upstream build workflow, source modification diff explaining `+dirty`, and preferably reproducible signed build receipts. Reject unsupported assertions of a clean binary.
2. Acquire and inspect exact bclone Git object and Go module dependency graph independently of the original GitHub runner; review unsigned object risk.
3. Authenticate downloaded Go 1.27.2 and NDK 28.2.13676358 package hashes, with trusted sources and acquisition logs. Record reviewer identity and explicit decision outside this overlay.
4. Only after reviewing all four values in a separate change may `source.lock.json` be modified; then run SB-Q02's independently clean two-lane workflow, assess full binary reproducibility, separate Android FUSE/device tests and signing.

**Devtool validates source contracts only.** No device, GitHub external approval, independent signatures, or final seal are issued by this overlay.
