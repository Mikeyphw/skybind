# NATIVE-06: signer disclosure polish hotfix (source-only)

## Device evidence and exact source

Source baseline: `3f022fcbf865fbd75eb1d94438ce013352032278`.
The rooted Android 16 NATIVE-06 readonly run's signed version-5 pair passed
`navigation`, `mount-ui`, `mount-consent`, and `config-consent`, but blocked at
`NativePolishUiTest#diagnosticsAndBkxStatesAreVisibleWithoutBackgroundActivation`.
Preserved evidence:
`~/.local/state/skybind/native-personal/native06-b0441d23b3ad42e7b606aa5844596a2e.json`
and its `polish.log` report:
`assertExists` failed to locate `TestTag = 'about-signer-sha256'` after opening
"View APK signing fingerprint".

## Root-cause hypothesis and implementation

Source shows a conditional signer card appended deep in the long More page's
`LazyColumn` item. The device log does not prove whether the missing semantics
node was caused by offscreen clipping, lazy content, or re-composition. Instead
of assuming a particular cause, the UI now presents the fingerprint in an
explicit Material `AlertDialog`, outside the scroll viewport. A named dialog,
fingerprint text node, and Close control are individually test-tagged. The
fixture checks the dialog is absent before opening, then present with a
fingerprint node after the user clicks, then absent after explicit closing.
The signer is still sourced from `NativePresentation.signer(context)`.

## Qualification safety

No root, daemon, signer, manifest, permission, or hosted workflow change.
These are normal read-only UI controls; no BKX activation is invoked by opening
the fingerprint dialog. The prior four successful device lanes remain historical
facts for version 5 only. New source requires new signed app + AndroidTest APKs,
strict exact-source preflight, and a full real-device NATIVE-06 rerun.
Source gate and unit tests cannot authorize release or device qualification.

## Delivery checklist

- [x] Source-level failure localized to conditional fingerprint reveal.
- [x] Dedicated accessible signer dialog replaces deep inline panel.
- [x] Test verifies initial absence, reveal, fingerprint existence and Close.
- [x] Negative tests defend fingerprint source, dismissal and test assertions.
- [x] Source-bound fail-closed application and postimage validation.
- [ ] GitHub Android compilation and personal APK verifier on new commit.
- [ ] Android 16 device confirmation of the `polish` lane and later lanes.
- [ ] Full device and owner qualification and final release seal.
