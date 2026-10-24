# NATIVE-05 — AndroidX protectionLevel aapt typed-integer compatibility (2026-10-24)

## Source and hosted evidence

- Exact input: Skybind GitHub `main` commit `bd24aa13640e1bd0e9c13653e87cef590eff28c9`, tree `ef2d3149c4b83b24aae4d2200e8e96b22394e1c5`.
- Hosted candidate run: https://github.com/Mikeyphw/skybind/actions/runs/40120472501. Application and AndroidTest APK compilation passed. `personal_apk.py create` rejected `COMPILED_MANIFEST_ATTRIBUTE_TYPE_INVALID:android:protectionLevel:app-personal.apk`; the candidate upload was skipped, so no signed pair was published or qualified.
- CI's bounded diagnostic reported five reviewed production permissions and `compiled_permissions: XML_PERMISSION_PARSE_UNAVAILABLE`, consistent with a compiled protection-level encoding not understood by the source parser. The raw compiled attribute wasn't retained. The precise serialized integer type is **not verified by that run**; `aapt`'s flag/enum type `0x11` is the concrete compatibility case covered in this source fix.

## Repair and intentionally unchanged security requirements

`aapt dump xmltree` may serialize the Android `protectionLevel` flag as `=(type 0x11)0x00000002`, rather than `=(type 0x10)0x2`. The verifier now accepts the `0x11` typed-integer encoding **only on** `android:protectionLevel`; it still requires the entire parsed 32-bit value to equal `2` (signature, no other flags). Other numeric manifest identity attributes retain their existing `0x10` format restriction. Quoted permission name and its single exact package-owned declaration remain mandatory. All unexpected, missing, duplicated or non-signature permission declarations are rejected.

The production APK must contain exactly the five reviewed requests (four app permissions plus the AndroidX-generated private receiver permission), both AAPT and compiled XML may not contain unapproved extras, the compiled test APK remains separately bound to its package and instrumentation target, and signer pin, production app versionCode/versionName, minimum/target SDK, immutable APK digests and GitHub source/run identity remain unchanged.

The source-only gate now verifies the dedicated flag parser is actually wired to `android:protectionLevel`. Unit tests exercise hosted-shaped `aapt` output using `0x10` and `0x11` forms plus failures for wrong typed tags, malformed/out-of-range integers, non-signature masks, extra protection flags, and reuse of `0x11` on SDK identity attributes.

## Acceptance and open gates

After applying this exact-source Devtool overlay and pushing its resulting source commit, the **new** GitHub hosted personal APK workflow must pass all of: compile app and AndroidTest, persistent signer checks, compiled package/version/SDK/permission/signature/protection verification, source-bound manifest emission, and publication of the paired APK artifact. If it still fails, inspect its actual bounded `compiled_permissions` diagnostics without accepting a weaker flag or guessed permission name. Source tests do not prove the hosted APK properties. NATIVE-06 installed-device instrumentation, matching module/daemon qualification, and explicit scoped owner approval remain separate, open gates.

Status after this source hotfix: `SOURCE_REPAIRED_HOSTED_CANDIDATE_PENDING`.
