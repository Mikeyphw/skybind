# Skybind NATIVE-05 AndroidTest compiled identity correction (2026-10-24)

## Observed evidence

GitHub Actions personal build [40103583694](https://github.com/Mikeyphw/skybind/actions/runs/40103583694) at `19cfccf812a2afc3afcc169d4cb3d6b6263d03f9` compiled the production and matching AndroidTest APKs and completed signing setup. Artifact verifier rejected AndroidTest with `COMPILED_MANIFEST_PACKAGE_IDENTITY_INVALID`. No artifact was published. The failure diagnostic invoked bare `aapt` through grep, unlike the verifier's SDK-resolved aapt, and did not disclose useful manifest metadata; the exact cause of the missing diagnostic lines was not established.

## Changes and limits

- The AndroidTest APK's compiled manifest may omit an independent test-package `versionCode`; retain `null` if it is truly absent, never fabricate a value. Production app MUST still have the explicit, monotonically increasing versionCode and exact versionName.
- AndroidTest must retain exact `io.github.mikeyphw.skybind.test` compiled package, exact `io.github.mikeyphw.skybind` instrumentation target, SDK 26/35, signed APK identity, signer equality and immutable SHA-256 for the hosted build. Malformed or conflicting present fields reject.
- A diagnostics script uses `personal_apk.aapt_bin()` and prints only bounded public field/element names and command status (not raw XML, secrets, or signing key material) to make any remaining mismatch actionable.
- The NATIVE-05 source gate and regression tests enforce these properties and presence of executable diagnostics.

## Required external gates

After source-bound Devtool application and push: verify source validation PASS; dispatch a fresh `skybind-personal-apk.yml` on `main` with versionCode greater than the installed APK. Require both signed APKs, candidate `PERSONAL_APK_MANIFEST.json`, source SHA/run/signing/hash verification and uploaded unqualified artifact. If still failed, inspect the **field-presence** diagnostics before changing parser again; no skip, fallback to source manifest, or qualification override is permitted. Only then proceed to guarded install, Android16 read-only and disposable full instrumentation, and separate owner approval.

**Current status: source-level repaired; GitHub build/metadata gate NOT YET RE-RUN; no qualification claim.**
