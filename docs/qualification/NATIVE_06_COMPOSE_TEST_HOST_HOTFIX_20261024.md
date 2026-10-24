# NATIVE-06 Compose instrumentation test-host repair — 2026-10-24

## Observed failure and scope

Live NATIVE-06 read-only acceptance on the signed personal candidate from GitHub run
`40124935243`, source `f6d48d49b33d8c92fc656885adda961afd8fb10c`,
installed app + test package on Android 16, reached the first `NativeUiTest` lane.
`navigation.log` recorded `Unable to resolve activity for: Intent { ...
cmp=io.github.mikeyphw.skybind.test/androidx.activity.ComponentActivity }` before
any Compose semantics assertion. The result was
`INSTRUMENTATION_FAILED_OR_SKIPPED:realNavigationHasFiveDistinctPages`.
No navigation assertion was exercised and device qualification was NOT granted.

## Root cause

`NativeUiTest` and `NativePolishUiTest` use `createComposeRule()` which requires
an `androidx.activity.ComponentActivity` host. The project has
`debugImplementation("androidx.compose.ui:ui-test-manifest")` but the personal
workflow deliberately selects `testBuildType=personal`, which is non-debuggable
and does not receive debug-only manifest dependencies. The compiled AndroidTest
package therefore had no launchable ComponentActivity.

## Repair

Add a single exported `androidx.activity.ComponentActivity` without launcher
intent or privileges to **androidTest/AndroidManifest.xml only**. Keep the
production personal manifest and Gradle build type unchanged. Add NATIVE-06
source validation and negative tests for wrong host, missing/unsafe export,
launcher intent, production contamination and extra permissions.

## Qualification truth

- Prior hosted pair passes bytes/signing, but **cannot** be reused for new
  NATIVE-06 qualification after source fix: its SHA and test APK are stale.
- Applying the overlay makes a new source commit. Push it and build a new signed
  personal **production + androidTest** APK pair from that exact SHA, with a
  strictly higher app versionCode than the installed version (installed 2,
  choose at least 3 subject to actual state).
- Verify that the **test APK's compiled manifest** includes the host and the
  app APK's compiled manifest does not, before performing an authorized
  non-downgrade in-place upgrade (no uninstall / no app-data clear).
- Run `native06_personal_acceptance.py run ... --profile readonly` with matching
  installed APK pair and clean exact source. Require every lane PASS, including
  navigation. If another lane fails, preserve and inspect its private log.
- Full profile requires a matching running daemon/module, prepared M3 fixtures,
  explicit opt-ins, and separate owner approval. No source-only pass is device
  qualification or release approval.

Evidence: previous NATIVE-06 private receipt at
`~/.local/state/skybind/native-personal/native06-ed1a289c135b43c8b4b5234568eb29a3.json`.
