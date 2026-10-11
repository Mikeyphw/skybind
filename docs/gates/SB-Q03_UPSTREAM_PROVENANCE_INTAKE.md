# SB-Q03 — Upstream provenance intake / review boundary

**Implemented as source code only, not run against real provider bytes here.**
Status of external attestations: `RAW_UNATTESTED`; **G01–G08 remain BLOCKED**;
final seal: `NOT_ISSUED`. No trusted pin is entered by this overlay.

## Operator workflow

1. On GitHub Actions, manually start **Skybind upstream provenance intake
   (RAW_UNATTESTED)** with the *explicitly selected* 40-character bclone
   candidate. The previously observed candidate was
   `7b63b1a4cc9d13465721ebbfc96f2f9bd810f600` — an observation,
   **not** a review-approved source pin. The workflow has no scheduled runs.
2. It requests the **official** GitHub API release and commit records and the
   exact `v1.75.0` NewFuture asset, fetches the candidate bclone Git object
   from the canonical HTTPS origin, and checks a clean detached checkout.
   SHA-256, release asset ID and size, module manifests, Git parent objects
   and any GitHub API signature-verification claim are recorded.
3. The generated JSON and metadata snapshots are an **untrusted evidence
   intake**. Anyone with control of the runner, downloaded inputs, or GitHub
   credentials could substitute them. Reviewers must authenticate custody,
   signing and source independently. A GitHub API `digest` and signed-tag UI
   are not independent supply-chain attestations.
4. Treat the reported candidate NewFuture digest and bclone commit as
   **review inputs only**. Do not copy values into `source.lock.json`
   until the independent pin review and Go/NDK toolchain decision are complete.
5. Only after reviewed pins are versioned and signed by the responsible
   authority may **SB-Q02's separate two-lane CI** be dispatched. Artifacts
   and build comparisons still do not automatically qualify a real Android
   device or authorize G01/G02–G08 or the final seal.

## Local offline inspection

For an already-acquired asset, exact detached Git checkout and two official
GitHub API JSON responses saved locally:

```bash
python3 scripts/dev/runtime/source_provenance.py collect \
  --newfuture-archive /private/inputs/magisk-rclone_arm64-v8a.zip \
  --bclone-checkout /private/inputs/bclone-detached \
  --release-json /private/inputs/newfuture-release.json \
  --commit-json /private/inputs/bclone-commit.json \
  --output /private/output/sb-q03-raw-review.json
```

This local command does not download, resolve mutable refs, modify the lock,
create keys, sign evidence or make gate claims. The output path must be new
and must not be within the bclone checkout. Incompatible metadata, wrong
hashes, unclean/attached Git checkout and mismatched source-lock fields fail
closed. An NDK directory may optionally be passed via `--ndk`; absence of an
observed NDK is **not a pass**. Termux-host Go version is an observation, not
an Android cross-compiler qualification.

## Toolchain security fork (no silent migration)

SB-Q02 currently pins Go **1.27.1** and NDK **28.2.13676358**, API 21.
Go **1.27.2**, released **2026-10-08**, contains security fixes.
Reviewers must choose whether to update the Go pin (updating the builder,
workflow, tests, lock and build evidence consistently) or formally document
why they keep the older compiler. Never change a pin solely to placate CI.
See <https://go.dev/doc/devel/release>.

## Trust exclusions

- API JSON, SHA-256 and Git references prove *consistency of observed inputs*,
  not authorship, source-code safety, signature validity or independent custody.
- `github_claims_signature_verified` preserves a **remote assertion** and
  cannot be used to promote a gate. No signing key, verified receipt or release
  seal is supplied by SB-Q03.
- The evidence tool is not a replacement for SB-Q02's pinned ELF/readelf,
  dependency, reproducibility and packaged FUSE-helper checks.
- No developer-machine or CI build is certified as device-working by this code.
