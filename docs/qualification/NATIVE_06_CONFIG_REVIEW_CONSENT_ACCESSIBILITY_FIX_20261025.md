# NATIVE-06 config consent missing from Android UI semantics — October 25, 2026

## Observed device failure

- Run 40158114373 built signed personal app/test APKs, versionCode 4, source `c767e42c4fb605f61bb9e0fc402e5b1c673b625b`.
- NATIVE-06 device receipt `native06-b682c5badeed49b38552fa949c80d520.json` proved three PASS lanes: `navigation`, `mount-ui`, `mount-consent`; then blocked at `NativeUiTest#configApplyRequiresReviewConsent`.
- Private instrumentation log: `AssertionError: Failed to inject touch input` because zero merged semantics nodes had `TestTag = config-consent` at `NativeUiTest.kt:110`.
- `config-editor-dialog` existed and `config-apply` was correctly disabled just before the missing checkbox. Therefore a test-host startup, package/signer, or navigation failure is NOT supported by this evidence.
- Root of missing semantics cannot be *fully proven* without UI hierarchy or live device instrumentation. The code does locate the checkbox in a bounded scrolling details area while keeping the disabled Apply action in a separate fixed footer. Material checkbox semantics may be merged/hidden. This patch hardens both suspected conditions.

## Repair

- Put a single click/toggle semantics owner `Role.Checkbox`, tagged `config-consent`, in a fixed dialog consent row below the bounded review-details scroll region and above the Apply/Close footer. Accessible label and checkbox act as one hit target.
- Render only for `step == 3 && preview != null`; preserve preview-ID-reset consent and disabled Apply until explicit consent and not busy.
- Reinforce instrumentation assertions for Off→On and exactly one Apply callback. No bypass of review/consent.
- Add source checks and negative mutations protecting visibility location, click semantics, preview lifecycle and disabled Apply contract.
- No root, daemon, signing, permission or package-policy modifications.

## Limits / remaining gates

Source tests and Go regression checks are not device verification. Rebuild the personal APK/test pair on GitHub from the resulting **new exact source SHA**, versionCode **strictly greater** than installed 4; fetch/verify and install only with explicit operator approval. Re-run NATIVE-06 read-only, retaining each newly failing lane's private log. Full mutation profile and owner approval remain unqualified.
