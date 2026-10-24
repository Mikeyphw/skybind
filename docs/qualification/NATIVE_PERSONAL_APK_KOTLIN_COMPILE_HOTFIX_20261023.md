# Skybind NATIVE-05/06 Kotlin compilation hotfix

## GitHub authority
- Failed personal APK run: https://github.com/Mikeyphw/skybind/actions/runs/40046033979
- Exact expected clean parent commit: `85f1007f4c720ad10fb645f7cd9ca676bda2b772` (tree `f156e35257ef9242d2d8559bade414238a6c36cc`).
- Diagnostic: Kotlin/JVM `setBkxKeepBackground(Z)V` and `setAutoConnectEnabled(Z)V` clash with the generated setters of their identically named Boolean properties; `:app:compilePersonalKotlin` fails.

## Promise/behavior checks
1. **BKX preference:** only rename explicit handler `setBkxKeepBackground` to `updateBkxBackgroundPreference`; state, persistent preference, service and UI callbacks remain intact.
2. **Automatic root preference:** only rename explicit handler `setAutoConnectEnabled` to `updateAutoConnectPreference`; session property stays observable and private-set, persistent preference and automatic reconnection remain unchanged.
3. **Defensive validation:** new fail-closed source guard scans Android main Kotlin files for direct generated-getter/setter method-name collisions. Unit tests replay the two failing classes and additional positive/negative examples; GitHub source workflow runs this guard.
4. **Gates:** exact source-bound preflight, per-file SHA-256 postimages, Python tests, native source/security gates, Go tests. Android Gradle compilation and AndroidTest/device/release status are NOT claimed from local tests.

## After application
1. `git status --short; git rev-parse HEAD; git push origin main`
2. Dispatch **a new** `skybind-personal-apk.yml` build for the new main SHA with `version_code` strictly greater than the installed version. GitHub Action `40046033979` cannot be reused for an approval because it failed and produced no APK.
3. Verify both hosted app/test APKs, signer and provenance, then run read-only and disposable full device acceptance using `docs/qualification/NATIVE_06_PERSONAL_APK_ACCEPTANCE.md`.

**Explicitly open:** hosted Android `assemblePersonal`, `assemblePersonalAndroidTest`, signing verification, module/APK matching, Android16 instrumentation and separate owner approval.
