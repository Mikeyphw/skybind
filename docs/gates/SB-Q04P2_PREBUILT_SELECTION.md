# SB-Q04P2 — official NewFuture prebuilt / selected build input contract

**Decision:** use the upstream `NewFuture/rclone-fuse3-magisk` v1.75.0 **prebuilt** (`magisk-rclone_arm64-v8a.zip`). Do **not** rebuild NewFuture. Compile only pinned bclone from source in the two separate disposable GitHub Actions lanes. This reflects the user's explicit choice of prebuilt over reproducible NewFuture source. It is **not** an independent approval of NewFuture's build custody.

## Selected immutable CI inputs

| Input | Selected value | Confidence |
| --- | --- | --- |
| NewFuture artifact | `NewFuture/rclone-fuse3-magisk` `v1.75.0` `magisk-rclone_arm64-v8a.zip` | Official release *location*, not signed custody |
| SHA-256 (NewFuture full ZIP) | `04ebfcc8c21c9583b7d4c723e2e69c1d3bbbd24432f6728ffbc2947e5282aa43` | SB-Q03 GitHub Actions download matched API digest (same trust domain) |
| bclone source commit | `7b63b1a4cc9d13465721ebbfc96f2f9bd810f600` | GitHub release revision corroborated; **unsigned** Git commit |
| bclone Go version | `1.27.2` | selected after official 2026-10-08 security release; exact downloaded tarball SHA pending |
| bclone NDK revision | `28.2.13676358` | selected Android NDK r28, exact downloaded package hash pending |
| bclone Android API | `21` | Skybind Android/arm64 build contract |

`source.lock.json` now selects those exact values. `source.selection.json` supplies an immutable, source-controlled engineering risk/selection record. `pin_selection.py` compares the entire lock and decision details and rejects modifications, forged statuses, altered exception scope, or claims of signing. Both the source CI and independent-build workflow execute the selection check. The builder enforces it for the repository's canonical lock; custom lock fixtures remain separate synthetic test inputs.

## Explicit limited prebuilt exception

At evidence intake time, NewFuture's release API reported `immutable=false`; the embedded rclone `v1.75.0+dirty` reported `vcs.modified=true`, Go `1.26.5` and NDK `r27d`, while the FUSE helper reported NDK `r27d`. The archive contains validated-looking Android/arm64 ELF files, but neither its source changes nor an authenticated upstream build receipt has been independently proven. The GitHub API digest is not an external cryptographic signature. **This provenance limitation is accepted only for acquiring/packaging/testing the exact prebuilt bytes. It is not waived for a signed release or device qualification.** Reject an archive with any different SHA-256 or suspicious ZIP/ELF structure; never silently follow newer tags.

bclone's selected Git commit is unsigned, and its entire dependency graph has not undergone an independent code audit. Two genuine Go 1.27.2/NDK 28.2.13676358 Android/arm64 builds and byte comparison have **NOT** been executed in this overlay. CI toolchain downloads need acquisition receipts, and the output must still be reviewed independently before any gate assertion.

## Evidence vs eligibility

Selection evidence: user-acquired SB-Q03 run `38099529777`; raw `RAW_UNATTESTED` release and commit snapshots; local SB-Q03R1 reconciliation `CONSISTENT_UNATTESTED`. This is operator-selected build input, **not** independent attestation of external source custody, code signing, device use, or release readiness. `source.selection.json` must keep `independent_attestation=false`, `real_builds_executed=false`, `android_device_tested=false`, `gate_g01=BLOCKED`, `final_seal=NOT_ISSUED`.

Next stage: merge source-selection PR, manually dispatch `.github/workflows/skybind-provider-reproducibility.yml`, retain both lane artifacts and raw comparison, inspect compiler/NDK acquisition and signed source custody limitations, then qualify physical Android FUSE/device behavior separately. Even if CI passes and both lanes are byte-identical, release gates and final seal must stay blocked until independently authorized evidence exists.

No build-time automatic provider upgrade, runtime switching, NewFuture source rebuilding, release publication, artificial signed proof, or gate promotion is introduced.
