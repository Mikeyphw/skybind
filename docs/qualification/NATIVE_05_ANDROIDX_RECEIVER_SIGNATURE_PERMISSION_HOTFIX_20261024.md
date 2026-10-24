# NATIVE-05: AndroidX generated signature receiver permission — CI 40119051809

## Observed hosted evidence

- GitHub Actions **40119051809**, exact source SHA `bfafb6268a978f46a1b3226fea7aae2709aa16be`, compiled `app-personal.apk` and `app-personal-androidTest.apk` successfully and prepared persistent signer. Release verifier returned `COMPILED_PERMISSION_DRIFT:app-personal.apk`. No manifest was published, no candidate APK uploaded; not device-qualified.
- Bounded real compiled-manifest diagnostics identified **exactly five requested production permissions**: `android.permission.ACCESS_NETWORK_STATE`, `android.permission.FOREGROUND_SERVICE`, `android.permission.FOREGROUND_SERVICE_SPECIAL_USE`, `android.permission.POST_NOTIFICATIONS`, and `io.github.mikeyphw.skybind.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION`. Both aapt permission listing and compiled XML agree. The compiled AndroidTest separately contains `android.permission.REORDER_TASKS`; this is not a production-app privilege.
- The last permission is injected by AndroidX Core for compatibility with `ContextCompat.RECEIVER_NOT_EXPORTED`. Android's documented app-owned permission declaration uses `android:protectionLevel="signature"`. It is not an unrestricted new permission grant.

## Implemented source correction

1. `scripts/dev/android/personal_apk.py` has an exact package-derived **five-permission production allowlist**, with NO regex/wildcard allowance for any other custom permission. Its compiled-binary XML tree parser examines direct `<permission>` declarations, rejects duplicates, requires the one allowed app-owned name, and requires compiled `android:protectionLevel` to be *exactly signature* (`0x2`). A missing declaration, different name, `normal`, `dangerous`, `signature|privileged`, or any other value is a hard rejection.
2. Production verification reads the compiled binary manifest **on every invocation**, even if the `aapt dump permissions` report already has five correct names; otherwise a malicious weaker declaration could pass unchecked. The binary must request the complete reviewed five permissions. Incomplete aapt reports can be reconciled against compiled XML; any aapt-only extra is still rejected. All package/version/SDK/debug/instrumentation cross-checks remain.
3. The manifest evidence stores `receiver_permission_signature_protected` from observed compiled XML, and `assert_pair` independently demands that verified state; signed artifacts/source/sha/known signer checks stay mandatory.
4. The source gate checks for the exact signature verification mechanism. Negative tests include missing/extra permissions, arbitrary custom names, missing definition, duplicated definitions, weaker/overbroad protection, and contradictory aapt reports. Diagnostic-only output includes the verified receiver declaration boolean, with no unfiltered XML, key material or private data.

## Gate status and next procedure

- Local source validation and Go tests are **not** proof of APK signature or compiled declaration in the hosted candidate. No release qualification is claimed from them.
- Apply the exact-source Devtool overlay to clean `bfafb6268a978f46a1b3226fea7aae2709aa16be`, push the resulting commit to GitHub `main`, and check `skybind-source.yml`.
- Re-dispatch `skybind-personal-apk.yml` with a **strictly increasing** installed versionCode; `2` is valid only if the installed app has a lower code.
- Require `Verify exact personal pair...` and `Publish source-bound, unqualified personal candidate` to PASS, and inspect `PERSONAL_APK_MANIFEST.json` for the precise five compiled production permissions, bound public signer, original APK SHA, test APK SHA, and `receiver_permission_signature_protected:true`. The AndroidTest permission is recorded separately and **must not be confused** with app capabilities.
- Only then continue NATIVE-05 device signer/upgrade preflight and NATIVE-06 read-only/full instrumentation, matching native module/daemon, and explicit owner approval. Do not conflate hosted candidate with qualified installed APK.

**Qualification state after this hotfix: SOURCE_REPAIRED_HOSTED_RESULT_PENDING.**
