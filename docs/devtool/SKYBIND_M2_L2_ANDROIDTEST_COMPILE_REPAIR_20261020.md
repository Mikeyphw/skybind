# Skybind M2-L2 hosted Kotlin test compilation failure (2026-10-20)

**Evidence:** GitHub Actions hosted-only Android run `39360456956` failed
at `:app:compileDebugAndroidTestKotlin`, source `91fe24de5b89e7a562f9c18873f44d7f3983518a`.
The source, JDK 17, Gradle, Android SDK and persistent signer checks passed;
no APK pair was published. Kotlin errors:

- `LiveUiAcceptanceTest.kt:5`: unresolved import `androidx.compose.ui.test.onAllNodes`
  (the API is available through the Compose test rule, not as this top-level import).
- `LiveUiAcceptanceTest.kt:32,34`: `getOrNull` unresolved because the semantics
  extension was not imported from `androidx.compose.ui.semantics`.
- `RemoteBrowserTest.kt:22,33`: positional `BrowserState` argument now binds to
  `onDisconnect: () -> Unit` after M2-L2 changed `SkybindApp`'s signature.

**Fix:** Remove invalid import, add `androidx.compose.ui.semantics.getOrNull`,
name `browser = BrowserState(...)` in both legacy fixture calls. Extend
`m2_ui_live_source_gate.py` and negative `test_m2_ui_live.py` regressions
for import and named argument contracts. Both previous M2-L1 and M2-L2
pre-existing receipts remain unmodified. This is a test-source-only change:
no daemon, app production, root grant, update policy or signing changes.

**Status:** SOURCE FIX PREPARED, GitHub APK compilation and M2-L2 live-device
qualification **pending**. The existing cumulative Devtool improvement ledger
`DEVTOOL_IMPROVEMENTS_CUMULATIVE_B1C_20261017.md` should absorb this
entry at the next source-snapshot update; this addendum preserves the full
evidence without introducing unrelated full-ledger rewrites into this hotfix.

**Devtool enhancement:** Source-only Android gates can miss Kotlin SDK
extension-import and changed positional arguments. Pair source regressions
with exact-version GitHub AndroidTest compilation as a mandatory acceptance
step, and maintain negative tests for changing Compose UI signatures.
