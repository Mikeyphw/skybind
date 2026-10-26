# NATIVE-06 v6 signer dialog: merged/unmerged semantics diagnostic

**Baseline:** exact clean `89eab0cca02f618c6a3c186e7bff8b3089c7bdbf`, tree `87b11072dea611d548e76bd61d1e3d6e6d85225d`.

**Device evidence:** latest NATIVE-06 read-only v6 receipt `native06-ca5a6c4f7d94486d8af8a2575011a0f6.json`, private `native06-logs-2b28f164eee0401ea69017d19c3546d7/polish.log`, hosted personal run `40329441768`. Navigation, mount-ui, mount-consent and config-consent PASS on v6; polish BLOCKED at `about-signer-dialog` **merged-tree** assertion, after the click returned. No evidence yet that the dialog itself failed to compose.

## Two-change merge-window decision

- **A — this change (test/diagnostic)**: retain production UI unchanged; after click wait for idle; record only 3 signer tags' merged/unmerged semantics node counts. Assert unmerged dialog, actual 64-character installed signer SHA-256 as displayed text, visible Close, and disappearance after closing. On assertion failure include the *bounded node-count string* in the instrumentation failure, never dump a raw semantics tree, fingerprint, device path, token or unrelated content. Expand source gate and negative tests to prevent assertion weakening.
- **B — deferred production-state repair**: hoist dialog state or change popup semantics only if the v7 on-device diagnostics demonstrate no composed dialog/fingerprint/Close in **either** tree. In particular, `showSigner` is presently remembered inside the More-page `Page()` body, which is one `LazyColumn` item; this is a root-cause hypothesis, not proof. Combining B now would conflate the cases and violate evidence-first remediation.

## Decision matrix

| v7 result | Interpretation / next change |
|---|---|
| Merged missing; unmerged dialog, SHA-256 and Close present; test PASS | API36 semantics query issue, no production rewrite. Continue official read-only lanes. |
| Unmerged outer dialog absent but content/Close present | Investigate Material3 dialog modifier semantics; do not automatically change app state. Device lane remains BLOCKED because this test still demands the dialog tag. |
| Unmerged dialog AND content/Close missing after click | Possible state/composition bug; implement a separate evidence-bound production fix (Change B). |
| Mixed/duplicate counts; invalid/missing SHA-256 or Close cannot dismiss | Fail closed, investigate the exact v7 private instrumented log. |

**Scope/assurance:** Only AndroidTest, source guard, regressions, docs and cumulative Devtool ledger change. No changes to production Compose, installed APK signing identity, permissions, daemon, release policy, NATIVE-06 runner, or device data. Source tests are not Kotlin compilation, real-device evidence, a release seal or owner approval.

**New exact-source pair required:** any commit of this diagnostic source invalidates the v6 exact-source assertion. Hosted workflow must build both app and AndroidTest for new commit and versionCode >= 7, verify signer/source/permission metadata, safely replace both in place only after the candidate reports `SAME_SIGNER_HIGHER_VERSION_UPGRADE`, and rerun `--profile readonly`. The previous four v6 PASS lanes are retained *historically*, not carried into new-source qualification. Installed-package operations must not include uninstall, `pm clear` or data wipe.

## Promise audit

- [x] Preserve current production dialog exactly (source diff).
- [x] Bounded merged/unmerged tag-count diagnostics and failure wrapping (source).
- [x] Unmerged dialog, signer text, close and disappearance remain required (source).
- [x] Both positive and mutation-negative source regressions (local Python).
- [x] Exact preimage source-bound Devtool transactional overlay (bundle).
- [ ] GitHub hosted production + AndroidTest compile on the resulting commit.
- [ ] Verified v7 signed pair, guarded in-place install, real v7 instrumentation.
- [ ] Any further production fix based on actual v7 per-tag evidence.
- [ ] NATIVE-06 remaining readonly/full profile, module and owner approval.

## 2026-10-26 — v7 hosted compile blocker and source hotfix B

Run [40394246393](https://github.com/Mikeyphw/skybind/actions/runs/40394246393) built from `3e8a9101476fcb5fc412b702dbf06eb934730873`. Source/signer admission and production Kotlin compiled, but the AndroidTest Kotlin task failed at `NativePolishUiTest.kt:88:34` (`Unresolved reference 'NativePresentation'`); zero APK artifacts published. The diagnostic's Java/Kotlin import of the UI package was missing; source-only Python checks did not catch it. **This is not Android 16 device evidence.**

Hotfix B explicitly imports `io.github.mikeyphw.skybind.ui.NativePresentation` in the test harness and adds strict source gate plus two negative mutation tests for missing or incorrect import. Source gate remains labelled source-only; final Kotlin compilation, paired-APK provenance verification and instrumented test are required. Original production UI, source A semantics diagnostics, signer, root permissions and data-preserving install policy are unchanged. Do **not** re-run the failed commit; dispatch a new v7 pair from the hotfixed exact HEAD after Devtool commits it and checks it into GitHub. VersionCode 7 is valid only if the installed app is older, the signer matches and guarded upgrade preflight explicitly permits it.

- [x] Pin failed run and actual compiler diagnostic to ledger.
- [x] Correct diagnostic test's Kotlin symbol import and negative source tests.
- [ ] Compile production+AndroidTest pair on the new commit.
- [ ] Verify APK, source SHA, persistent signer; run preflight before any install.
- [ ] Re-run NATIVE-06 readonly and interpret bounded merged/unmerged tags.
