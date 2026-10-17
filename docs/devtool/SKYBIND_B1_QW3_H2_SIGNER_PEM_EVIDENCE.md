# Skybind B1-QW3 H2: APK signer-certificate evidence hotfix

**Observed failed hosted source:** `b35cc0d2313b96e4546cba190e38de483dc16a75` (2026-10-17).  
**Observed failure:** `scripts/dev/android/apk_manifest.py create`: `FAIL_CLOSED`, `APK certificate fingerprint unavailable`.

## Evidence and scope

- The Android SDK installation issue was resolved by QW3-H1. The hosted Gradle job compiled **both** `assembleDebug` and `assembleDebugAndroidTest` successfully (`BUILD SUCCESSFUL in 2m 18s`, 66 tasks).
- Manifest generation blocked afterward. The old parser required the exact human-readable label `Signer #1 certificate SHA-256 digest:`. Android AOSP tools also emit `Signer (minSdkVersion=..., maxSdkVersion=...) certificate ...` labels. The exact certificate stdout was not included in the failure log, so this is a supported compatibility hypothesis, not proven byte-level root cause.
- H2 requests `apksigner verify --print-certs-pem` and derives SHA-256 from the one DER-encoded X.509 certificate returned *after successful signature verification*. It never trusts a human-readable signer-label digest and never synthesizes a fingerprint from the APK hash.
- If `apksigner` is absent in a non-CI environment, offline hash verification still reports `PASS_LOCAL_HASH_ONLY_CERT_UNCHECKED`, but hosted manifest **creation rejects** missing signer evidence.
- Missing/malformed/ambiguous PEM and failed `apksigner verify` are rejected. Different app/test signing identities remain rejected.
- No local Gradle builds, new GitHub runs, device installs, or release seals are performed by the overlay.
- Existing failed GitHub runs and Devtool pipeline receipts remain unchanged.

## Qualification

- Python source contract tests cover numbered and SDK-range signer labels, rejecting missing, corrupt, duplicated and invalid certificates, verifying cryptographic-verification exit status, and refusing different app/test signer IDs.
- On-host real certificate verification is **not demonstrated here**; it requires another hosted run on the new commit.
- Production cross-app broker and B1-C device acceptance remain unqualified.

## Apply

Use the bundled source-bound artifact from the user's Termux repository with
`devtool -r "$PWD" --yes apply-overlay "$tmp/overlay.zip"`. The clean-tree,
source checks, validation and atomic rollback are mandatory.

Then run:

```sh
./devtoolw r1-hosted-source
git status --short
git push origin main
devtool -r "$PWD" actions pipeline plan --file docs/devtool/r1_android_hosted_pipeline.json --auth gh --json
```

Start a **new** pipeline, not a retry of the pre-hotfix source. Once the new
run succeeds, resume that new pipeline and check the hosted APK pair's Devtool
artifact attestation before any device acceptance.
