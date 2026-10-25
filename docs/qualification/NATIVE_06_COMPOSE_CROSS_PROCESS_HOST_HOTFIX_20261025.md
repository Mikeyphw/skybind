# NATIVE-06: correct-process Compose test host (24–25 October 2026)

## Device evidence and exact failure

The hosted version 3 signed pair, [GitHub Actions run 40135828322](https://github.com/Mikeyphw/skybind/actions/runs/40135828322), source `4ccbed5138d0af413fcb42318429cf5024a9c9c4`, installed on Android 16 with both APK hashes verified. The first NATIVE-06 read-only navigation lane failed before executing UI assertions:

`Intent in process io.github.mikeyphw.skybind resolved to different process io.github.mikeyphw.skybind.test: ... cmp=io.github.mikeyphw.skybind.test/androidx.activity.ComponentActivity`

A previous test-only manifest fix created `ComponentActivity` in the **test APK**, but Android instrumentation starts activities in the **target app process**. Both source-only and hosted build gates passed previously; neither validates actual process ownership. The device's negative receipt is authoritative.

## Scope

- Use `createAndroidComposeRule<MainActivity>()` for NativeUiTest, NativePolishUiTest and RemoteBrowserTest, selecting the app's already-declared target-process activity.
- Fixture tests replace MainActivity Compose content using AndroidX `activity.setContent` from the UI thread after resolving the activity off that thread, rather than `compose.setContent` (which cannot replace preexisting content).
- Remove the test APK's explicit ComponentActivity host. Do not add production app components, permissions, exported activities, debug flags or service authority.
- Keep the existing strict NATIVE-06 parser, signature, identity, negative/skipped tests and root manager scope checks.
- Source gate rejects wrong-process test host, production fixture component, changed target activity, incorrect rule, unsafe Gradle variant or direct `compose.setContent`.

**Known limitation:** Launching real `MainActivity` invokes its ordinary onStart/foreground behavior before fixture injection. Tests must prove that fixture expectations remain isolated; no claim of actual device PASS until recorded by NATIVE-06. Tests are source-only and do not independently prove Kotlin compilation or Android behavior. No current APK remains qualified after this source change.

## Required follow-up

1. Apply to exact clean Git HEAD `4ccbed5138d0af413fcb42318429cf5024a9c9c4`, confirm validation receipt, push new commit.
2. Dispatch hosted `skybind-personal-apk.yml` with `version_code=4` only if installed version remains 3; select strictly greater otherwise.
3. Inspect actual GitHub build, signer, compiled app/test package manifests, paired hashes and candidate artifact. A passing build is still **candidate only**.
4. Fetch candidate and guarded in-place upgrade both APKs preserving data; require `ALREADY_INSTALLED_IDENTICAL_PAIR` on postflight.
5. Run `native06_personal_acceptance.py run --profile readonly`; evaluate full saved navigation.log and ALL required lanes. Do not reinterpret a failure as PASS or reuse an old receipt.
6. For full acceptance, produce and activate same-source module/daemon, run `--profile full` only with isolated fixtures and explicit mutation consents; require new exact device and separate owner approval receipts.
