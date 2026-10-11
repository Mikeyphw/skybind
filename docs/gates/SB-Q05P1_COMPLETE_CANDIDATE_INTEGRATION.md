# SB-Q05P1 — bind real Q04 provider bytes into complete Skybind candidates

**State: SOURCE INTEGRATION IMPLEMENTED; DEVICE NOT TESTED; G01–G08 BLOCKED; FINAL SEAL NOT_ISSUED.**

The Q04 run `38110749243`, source revision `429a7cb5ba3be3ebcaed9e0cae804065dc4a65fe`, contains two distinct successful CI lanes. Its raw evidence was re-hashed, and candidate input hashes are recorded in `scripts/dev/integration/q04.inputs.json`. This repository selection is **not** an external signature or independently authenticated supply-chain approval.

The new manually dispatched `skybind-candidate-integration.yml` workflow checks out Skybind on `main`, downloads that *specific* Q04 run from `Mikeyphw/skybind`, checks run/job statuses, commit, both lane receipts and unmodified provider ZIP SHA-256s, and checks exact binary/ZIP equality. It then compiles the complete Skybind daemon for Android/arm64 with Go 1.27.2, CGO disabled, and embeds the existing source-controlled module hooks and original WebUI. The existing `skybind_release.py` verifier independently checks the full module candidates.

Both providers are packaged separately: `newfuture` retains the **official prebuilt** and the original `fusermount3`, while `bclone` packages exactly the separately built Q04 executable and the same helper. The prebuilt provenance exception is explicitly bounded to unqualified development/testing; no NewFuture rebuild is attempted.

This implementation also repairs a real cross-campaign compatibility bug: static-helper provider packages from Q04 contain **exactly two** runtime ELF entries. The full-module release verifier previously rejected them by requiring three or more. It now accepts two *only* for the known `reviewed_static_helper_layout`, requires the provenance inventory match all installed system provider files, and continues to require a real FUSE library for `shared_libfuse` mode. The additional `system/bin/skybind` binary is verified by the outer candidate manifest, not misrepresented as part of the upstream provider receipt.

## Non-promotable outputs

- `skybind-newfuture-CANDIDATE-UNQUALIFIED.zip`
- `skybind-bclone-CANDIDATE-UNQUALIFIED.zip`
- `candidate-evidence.json`, `candidate-summary.json`, pinned Go build information

All candidate archives retain `CANDIDATE_ONLY_NOT_SEALED`. They are **not** G08-approved installers or verified releases. No install/reboot/device action, gate promotion, trust signing, or final seal is part of the CI workflow. Android root-manager installability, cross-app FUSE behavior, crash recovery and WebView require opt-in *physical-device* evidence with independently verified Devtool receipts. **Do not flash these candidate ZIPs as a production release.**

Missing/tampered run metadata, mismatched original prebuilt source hash, unequal lane bytes, changed build receipts, symlinked input, missing helper or inappropriate release claims must remain fatal. The Q04 result is raw reproducibility evidence and cannot alone satisfy the unchanged G01 gate requirement for independently reproducible NewFuture source provenance; resolving that policy conflict requires separate authority.
