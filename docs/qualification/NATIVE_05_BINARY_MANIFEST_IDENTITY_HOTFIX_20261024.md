# NATIVE-05 signed APK verification recovery — 2026-10-24

## Observed evidence

- GitHub personal APK run **40055856085** at source `f08cdf6134bf9efe0dac205f169ecf4c28fc9a08` built and signed the production APK and AndroidTest APK successfully; candidate publishing never ran.
- The producer refused the second APK with `COMPILED_PACKAGE_IDENTITY_UNAVAILABLE:app-personal-androidTest.apk`. The exact badging output was not retained. The prior change allowing empty AndroidTest `versionName` was insufficient. The remaining cause is a **badging parser-to-generated-test-package mismatch**, not proven invalid APK identity.
- The producer must not invent metadata, waive signer/permission/target checks, or publish unverified bytes.

## Implemented bounded repair

- Prefer exact `aapt dump badging` for valid package identity; if missing/unusable, use `aapt dump xmltree <APK> AndroidManifest.xml` and parse typed attributes from the **compiled** manifest, rather than source strings, as an authoritative fallback.
- Track root element and direct children, rejecting absent or duplicate package/version attributes, nonnumeric version codes, missing sdk, ambiguous integer types, and badging-versus-binary-manifest disagreements.
- A generated AndroidTest package may use versionCode `0`, but only if it is explicitly present in compiled metadata; the personal **app** version must still match the requested strictly increasing version code and exact version name. A nonnumeric or missing code never silently defaults to zero.
- Maintain hard checks for application/test package IDs, pinned signing certificate equality, test instrumentation target, exact declared app permissions, provenance, artifact checksums, debug state, and no owner release claims.
- On failed verification, print only bounded public binary package/version/sdk/target metadata for both compiled APKs to the GitHub run log; no keystore material, secrets, app data, or unverified artifact is published.
- Add positive/negative tests covering malformed binary manifests, duplicate attributes, mismatches, test code 0, and the new failure diagnostics. Extend `native05_personal_apk_gate.py` contract and the existing source CI suite.

## Promise evidence / remaining gates

| Promise | Evidence | State |
|---|---|---|
| Binary-manifest alternate reader | `personal_apk.py` parser + tests | SOURCE_DELIVERED |
| Fail-closed package and signer chain | `assert_pair`, `file_record`, `verify_manifest`; unchanged other guards | SOURCE_DELIVERED |
| User-friendly failure evidence | GitHub personal workflow failure-only diagnostics | SOURCE_DELIVERED |
| Source regression integration | `tests.test_native05_personal_apk` under GitHub source workflow | SOURCE_DELIVERED |
| Hosted APK verification | Fresh GitHub run bound to post-hotfix commit | OPEN |
| Signed candidate artifact | Only if hosted verification succeeds | OPEN |
| Android device and root/module acceptance | NATIVE-06 actual device runner and owner approval | OPEN |

No old source validation or personal module approval qualifies a new APK byte pair.
