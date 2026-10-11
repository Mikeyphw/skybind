# SB-Q02 — Pinned Android/arm64 provider reproducibility (source implementation)

**Status: SOURCE CONTRACT IMPLEMENTED; REAL INDEPENDENT BUILD NOT RUN; SB-G01 BLOCKED; FINAL SEAL NOT_ISSUED.**

The original Rclone Nexus `runtime-source-build.yml` and `runtime_source_build.py` informed
this Skybind-only design. This carries forward immutable full-commit checkouts,
Go `1.27.1`, NDK `28.2.13676358`, API `21`, CGO arm64, Go read-only module graph,
isolated caches, ELF inspection, real checksums, and deterministic build metadata.
It deliberately omits scheduled mutable-ref resolution, dynamic runtime upgrades,
runtime activation, publish-on-build, and automatic release creation.

## Pin review and provenance

`source.lock.json` remains **unmodified** by SB-Q02. In particular, `newfuture.archive_sha256`,
`bclone.commit`, `bclone.ndk_revision`, and `bclone.go_version` remain `null` until a
human/independent supply-chain review authorizes exact values. Earlier NewFuture and
bclone inspection reports are **RAW_UNATTESTED**; never copy them into the lock on
an automated path. A passing lock syntax/format check cannot authenticate the
upstream GitHub asset, commit ancestry, runner, or external review.

The NewFuture v1.75.0 arm64 asset supplies the single unchanged canonical
`fusermount3` and any shipped libfuse siblings. The reviewed v1.75.0 layout
normally has **statically linked FUSE** and no `libfuse*.so`. ELF checks validate
architecture, Android linker and dependency inventory, but do **not** by themselves
prove that static FUSE works on a device.

`source_build.py` supports `pins`, `verify-newfuture`, `build`, `verify`, and `compare`.
The build refuses branch refs, dirty/untracked/attached Git checkout state,
nonofficial origin, a wrong compiler, unreviewed pins, missing `go.sum`, mutable
Go module graph, output directory reuse, wrong ELF ABI/interpreter, and
unexpected dynamic dependencies. It never consumes ambient module/build caches.
It generates `rclone`, canonical `provenance.json`, and `SHA256SUMS`, then verifies
all output bytes. NewFuture and bclone package assembly uses the shared verified
FUSE helper authority in the existing static-runtime packager.

## CI and Devtool

The opt-in `.github/workflows/skybind-provider-reproducibility.yml` creates
**two separate clean Ubuntu runner jobs A and B**, each with its own private source
checkout, pinned toolchain, disposable Go cache, NewFuture asset verification,
and deterministic **both-provider** ZIP assembly. A dependent third job downloads
and checks both actual build artifacts, exact bclone binaries and package bytes.
A missing lock pin fails the CI workflow; it is never silently skipped as PASS.
The existing source CI now runs the local Q02 negative/contract suite, and Devtool
runs `scripts/devtool/check_q02_source_build.sh` during overlay application.
These tests use synthetic fixtures, not verified external provider builds.

The comparison result intentionally says `BYTE_IDENTICAL_UNATTESTED` and does not
create `build/evidence/sb_g01_provider_builds.json` or any signed release receipt.
The existing SB-G01 verifier still requires its independently authenticated
source evidence; its historical evidence contract is not watered down by Q02.

## Outstanding external requirements

An independent reviewer must authenticate the official NewFuture release asset
and SHA, the exact bclone Git revision, NDK/Go provenance and dependency graph;
then approve the source lock in a separately reviewed change. Afterward, two
actual clean CI build lanes must run on supported external runners and their
published checksums, raw run receipts, source ancestry and artifacts must be
collected/verified independently. Signature/attestation verification, actual
Android device FUSE mounts and ordinary-application read/write, root-manager
matrix and endurance coverage are **still mandatory** before G01/device gates
or the final seal can be considered. A green source-only test is not a gate pass.

**Termux note:** The pinned recipe requires the Linux x86_64 NDK prebuilt host.
Do not pretend that Android/Termux-native clang is identical or that a device-local
Go build satisfies the independent Ubuntu CI lane requirement.


## SB-Q03R1 subsequent policy update (2026-10-10)

The **future bclone build** compiler version is now **Go 1.27.2** (security revision), while the NDK remains `28.2.13676358`. Any earlier Go 1.27.1 reference on this page is historical to the original SB-Q02 implementation. See `docs/gates/SB-Q03R1_TRUST_PIN_REVIEW.md`. No upstream trust pin has been populated, and no device or G01 evidence has been attested.
