# NATIVE-05 CI 40117550163 — compiled permissions report reconciliation

**Evidence:** [GitHub Actions personal APK run 40117550163](https://github.com/Mikeyphw/skybind/actions/runs/40117550163), source `3f09ec5c08021c4503b47dd4b5faa06a3dde3a17`, successfully compiled both the production personal APK and its matching AndroidTest APK with the pinned persistent signing setup. The package-identity branch now proceeded beyond its previous failure, but `personal_apk.py create` returned `COMPILED_PERMISSION_DRIFT`. The run did not publish an artifact. The diagnostic output for this run contained only package/version fields, **not a permission inventory**; it is not possible to claim the compiled APK had exactly the expected four permissions.

## Implemented repair (source only)

1. Keep the reviewed personal app permission allowlist unchanged: `FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_SPECIAL_USE`, `POST_NOTIFICATIONS`, `ACCESS_NETWORK_STATE`.
2. Treat `aapt dump permissions` as a secondary inventory. If it lists an **unexpected** permission, fail immediately. If it omits one or more, do not presume that they are absent from the APK. Instead parse the **compiled APK** `AndroidManifest.xml` with the existing depth-aware binary XML parser, require its permissions to match **exactly** the approved four, and cross-check compiled package/version/SDK/debuggable/instrumentation against the values from badging. Deny malformed, contradictory, missing or expanded permissions.
3. Extend the verifier's failure-only diagnostics to report bounded public permission names and missing/extra inventories from both SDK report and compiled APK. Print neither entire XML nor signing/keystore content. These are diagnostic-only records, never approval evidence.
4. Add positive tests for incomplete reports backed by correctly compiled manifests and negative tests for APKs genuinely missing/adding permissions, unexpected `aapt` entries, and mismatched package/version. Update the cumulative Devtool improvements ledger.

**Confidence and limitation:** Source regressions prove behavior on crafted authentic-format `aapt` snippets, not the unknown contents of CI run 40117550163. If the next CI run reveals an actually added merged permission, the verifier is expected to **continue blocking**; investigate and remove or explicitly review that privilege rather than weakening the allowlist. This is not a signed-release gate pass. No APK/data is installed, revoked, modified or qualified by this source overlay.

## Required post-hotfix gates

- Source validation on the newly pushed exact commit.
- Re-dispatch `Skybind Personal APK (candidate only)` using a version code **strictly greater** than the installed APK's. Do **not** rerun failed run 40117550163 against old commit bytes as qualification evidence.
- Inspect `Verify exact personal pair, package identity, signing and release metadata`. If it fails, read the `permissions_report` and `compiled_permissions` sections in the `Bounded compiled APK metadata diagnostics on verifier failure` job step and compare missing/extra entries. An actual permission expansion is a source-release blocker requiring manifest-merger diagnosis.
- Require a successful published pair (`app-personal.apk`, `app-personal-androidTest.apk`, `PERSONAL_APK_MANIFEST.json`) and independent device verification before any NATIVE-06 instrumentation/owner approval.
