# Skybind NATIVE-05/06 AndroidTest import compilation repair

- **Failing hosted run:** https://github.com/Mikeyphw/skybind/actions/runs/40051717952
- **Exact clean baseline:** `7366223ab386babbbcc76747d765c98522ff6097` (Git tree `8cddfdd910a0103f8629ad1a65e6307858b95547`).
- **Compiler gate:** `:app:compilePersonalAndroidTestKotlin` failed on three `Unresolved reference` imports. `:app:compilePersonalKotlin` and `:app:compilePersonalJavaWithJavac` passed. No personal artifact or signing receipt was emitted.

## Promise-by-promise correction

1. **Live Android test:** delete invalid `assertExists` import; preserve runtime UI assertion calls and all mount/root test behavior.
2. **Polish Android test:** delete invalid `assertExists` and `assertDoesNotExist` imports; preserve diagnostics, activity, and screenshot assertions.
3. **Prevent regression:** extend pre-existing source guard across every `android-app/app/src/androidTest/**/*.kt`, reject those exact invalid imports, and add positive/negative tests. CI source validation calls the guard already; its step is renamed for clarity.
4. **Evidence truth:** preserve separately the completed application Kotlin/Java compilation gate versus open AndroidTest compilation; local static tests are NOT a hosted Gradle build. No claimed installed candidate, device result, root manager upgrade, or personal APK owner approval.

## After Devtool applies this exact-source overlay

1. `cd ~/Code/skybind; git status --short; git rev-parse HEAD; git push origin main`
2. Dispatch a NEW `skybind-personal-apk.yml` workflow on `main` with versionCode above the installed package. Since both failed runs produced no candidate, the same previously attempted versionCode can be reused if valid.
3. Check the actual workflow's **app + AndroidTest compilation**, manifest/signer verification, and published artifact. If successful, continue with `scripts/dev/android/personal_apk_device.py fetch`, then explicit app+matching module device qualification from `docs/qualification/NATIVE_06_PERSONAL_APK_ACCEPTANCE.md`.

Do not treat the old failed run or previous M2/M3 and personal module approval as evidence for a new APK.
