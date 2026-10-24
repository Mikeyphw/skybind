# NATIVE-05 AndroidTest badging empty-code hotfix — 2026-10-24

## Evidence and root cause

- Failing hosted personal APK run: [40109002928](https://github.com/Mikeyphw/skybind/actions/runs/40109002928) on `c680f317e7c75395f4b1699b7568e98cd9bb16d0`.
- Exact result: `COMPILED_PACKAGE_IDENTITY_UNAVAILABLE:app-personal-androidTest.apk`. Both `assemblePersonal` and `assemblePersonalAndroidTest` succeeded, as did SDK provisioning and persistent signing preparation. Artifact creation and publication were correctly blocked.
- The bounded CI diagnostics proved that **compiled** AndroidTest XML contains `package`, `uses-sdk`, `instrumentation android:targetPackage` but **no** `android:versionCode` or `android:versionName` attributes. `aapt dump badging` had a `package:` line, but the diagnostic intentionally did not expose the versionCode value. The empty-code badging case is a strong explanation, reproduced in tests, **not a claim that raw hosted bytes were examined**.
- Prior source accepted missing `versionCode` but rejected `versionCode=''` in `aapt badging` **before** reading compiled XML. This defect is also independent of Go daemon/Android Kotlin compilation.

## Fix and security policy

1. On **AndroidTest only**, recognize an explicitly empty `versionCode=''` as *absent*, recording `null` rather than inventing a number. Production APK still requires a nonempty numeric version and exact requested versionName.
2. Always inspect the AndroidTest **compiled binary XML manifest**, whether or not badging has a successful `package:` line. The authoritative package name, SDK, instrumentation target and any version fields come from this binary XML, not Gradle assumptions.
3. Require matching nonempty badging package names; reject malformed, ambiguous, duplicated, or contradictory fields. A badging code of `0` is tolerated alongside *absent compiled XML code* as a synthesized test-only default, never recorded as a real compiled code. Any other concrete disagreement is rejected. Reject wrong instrumentation target, signer, bytes, SDK, or app version as before.
4. Classify only `name`, `versionCode` and `versionName` as **present/empty/absent/duplicate** in hosted diagnostic output, without printing raw values, APK bytes or signing secrets.
5. Add positive AndroidTest + real CI-shape mock tests and explicit negative tests for wrong package, `versionCode='3'` with absent binary code, invalid quoted and unquoted code, duplicate fields and app-empty code. Existing metadata/provenance/install gates stay enabled.

## Gates, evidence and limitations

- Source gating: native Python regression suite, code parser gate, full Go backend suite, exact source/postimage SHA-256, wrong-commit and dirty-source rejection.
- External gate **NOT YET CLAIMED**: GitHub hosted `personal-apk.yml` for the post-hotfix commit must complete `personal_apk.py create` **and** `verify`, publishing `skybind-personal-apk-candidate-unqualified` containing the exact app APK, AndroidTest APK, and `PERSONAL_APK_MANIFEST.json`.
- Next: fetch the published artifact using `personal_apk_device.py fetch`, check run SHA/signer/bytes and installer preflight on the selected Android 16 device, match same-source daemon/module, run read-only instrumentation before consent-scoped full tests; review and approve only after full device receipts.
- Historical personal *module* approval is unrelated; no APK/device/independent qualification is implied by this hotfix.
