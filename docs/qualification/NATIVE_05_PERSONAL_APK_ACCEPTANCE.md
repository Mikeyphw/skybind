# NATIVE-05 — Personal signed APK lane, source delivery and executable acceptance

**Status:** source implementation delivered; hosted Android compile/device/owner approval still require independent actual execution. This does not revise a previously approved Skybind personal module ZIP.

## Source-bound promises

| Roadmap promise | Delivered implementation | Positive/negative source evidence | Status |
|---|---|---|---|
| Hosted **separate** personal APK + AndroidTest lane | `.github/workflows/skybind-personal-apk.yml`; `assemblePersonal` + `assemblePersonalAndroidTest`, dispatch main only | `native05_personal_apk_gate.py`, personal test suite | SOURCE DELIVERED — hosting run pending |
| Deterministic/versioned personal app while preserving package ID | `build.gradle.kts`: explicit integer 2..2100000000 and `0.2.0-personal.<code>`, stable `applicationId`; debug channel version unchanged | negative Gradle source gates, compiled aapt verifier | SOURCE DELIVERED — compiled version pending |
| Non-debuggable personal app | dedicated `personal` build type (`isDebuggable=false`), no debug fallback | `personal_apk.py` checks compiled app badging | SOURCE DELIVERED — compiled bit pending |
| Same owner-pinned signer, personal+test pair | existing encrypted CI persistent keystore; same `skybind_dev` key for both; `ci-prepare` pin; `apk_manifest.apk_cert()` for each byte artifact | pair mismatched-cert tests and signer pin tests | SOURCE DELIVERED — CI signer observation pending |
| Source/toolchain/artifact provenance | `PERSONAL_APK_MANIFEST.json` records GitHub SHA/run/attempt/ref, AGP/Gradle/JDK/SDK, compile invocation, both exact APK SHA-256/sizes, signing cert pin, version metadata | source/run/bytes negative tests | SOURCE DELIVERED — real receipt pending |
| Manifest permission & capability inventory | `aapt dump permissions/badging` from actual binary, exact reviewed production five-permission allowlist (four explicit Android permissions plus one AndroidX Core app-owned signature-only receiver permission verified in compiled XML) and root AIDL/service manifest source digests; permission drift blocked | negative permission/test target/debug/version tests | SOURCE DELIVERED — actual aapt test pending |
| SVG/adaptive launcher/name/splash/notification | NATIVE-01 SVG-generated adaptive and monochrome resources retained; `@string/app_name` = Skybind; dedicated white status icon; platform splash uses launcher icon | updated foundation branding gate and N05 source gate | SOURCE DELIVERED — visual launcher/splash tests pending |
| Hosted candidate download and verifier | `personal_apk_device.py fetch` checks GitHub run status/workflow/branch/source and exact three downloaded files; locally pinned signer, binary metadata | source tests + negative manifest cases | SOURCE DELIVERED — live GitHub fetch pending |
| Nondestructive signer-compatible in-place upgrade | `personal_apk_device.py device`: default inspection; explicit `--install`, pull existing app and test, verify signer and version strictly increases, no uninstall/-d/data clear, verify post-install bytes again | mocked trust/version/partial-installed tests | SOURCE DELIVERED — installed real device pending |
| Separate scoped candidate (not previously approved personal ZIP) | `PERSONAL_APK_CANDIDATE_ONLY`, `device_qualified:false`, `owner_approved:false`, `release_qualified:false`; only NATIVE-06 may accept it | overclaim negative test | SOURCE DELIVERED — candidate and acceptance pending |
| Android API 36 / startup, mount and proof negative matrix | Existing instrumented test source remains included in assembled AndroidTest APK | device procedure below | EXTERNAL GATE OPEN (not a missing N05 source component) |

## Intended operator procedure (no silent installs)

1. Commit/push this source to `main`. Keep the previously approved module ZIP/digest untouched. Ensure `SKYBIND_ANDROID_KEYSTORE_B64`, `SKYBIND_ANDROID_KEYSTORE_PASSWORD`, `SKYBIND_ANDROID_SIGNER_SHA256` still reference **the existing** persistent signing key. If that certificate differs from the installed app, the in-place upgrade is **blocked**. Never silently rotate signer.
2. Run GitHub workflow `Skybind Personal APK (candidate only)` via Actions, dispatch from `main` with an explicit strictly increasing `version_code` (e.g. `2` only if older installed versionCode is `1`). Inspect compile, source and signer receipts; hosted output **must** contain `app-personal.apk`, `app-personal-androidTest.apk`, `PERSONAL_APK_MANIFEST.json`.
3. On the Termux/ADB machine: `python3 scripts/dev/android/personal_apk_device.py fetch --run-id <REAL_RUN_ID>`. This stages a fully-verified pair in `~/Downloads/Skybind-Personal-APK-<RUN_ID>` and writes a machine receipt under `~/.local/state/skybind/personal-apk/`. The trusted signer pin is read from `~/.local/share/skybind/signing/signer-sha256.txt`. `gh`, `aapt`, `apksigner` and `adb` should be installed; the local script does **not** build the APK.
4. Dry-run without any install: `python3 scripts/dev/android/personal_apk_device.py device --folder "$HOME/Downloads/Skybind-Personal-APK-<RUN_ID>" --serial <REAL_ADB_SERIAL> --source-sha <EXACT_SOURCE_SHA>`.
5. Only after reviewing preflight and confirming an allowed in-place upgrade: repeat with `--install` added. The installer never uninstalls or clears data. Any partial installation error stays an error: inspect device state before retry.
6. Run NATIVE-06 automated mounted/root-negative acceptance with the **matching newly installed app and test APK**, using disposable test-owned mounts and explicit permission for writes. Record source SHA, signer, APK bytes, tested root manager/API and device receipts. Test Android 36, initial root prompt/denial/reconnect, Mounts list/lifecycle/editor/rollback, Browser/Jobs/Activity/BKX state, crash/reconnect and invalid/replayed proof negatives.
7. Record a separate user owner approval for the exact signed APK and evidence; **do not** claim `PERSONAL_NATIVE_APK_APPROVED` until those gate checks genuinely pass.

## Explicit blockers and boundaries

- This is a hosted-only Android build. The source tests do **not** prove that `assemblePersonalAndroidTest` compiles or that the existing persistent signing secrets are present. A hosted run must confirm both.
- Same applicationId with a changed key cannot be upgraded in place. A different-signer migration must be explicitly planned and tested outside this default pipeline; this workflow will not uninstall or erase data.
- A downloaded JSON manifest alone is **not independent GitHub attestation**: `fetch` verifies the live GitHub run identity and exact downloaded bytes; offline local verification only proves internal consistency plus the owner's external signer pin.
- Android's package installer is not transactional across the app and AndroidTest package. If the second install fails, a partial pair can exist and is reported as failure, never a PASS.
- Real physical-device acceptance, icon masks, UI screenshot evidence, signer continuity from an actual installed old APK and NATIVE-06 approval are not generated by NATIVE-05 source implementation.

## NATIVE-05 compiled protectionLevel source compatibility (2026-10-24)

CI run [40120472501](https://github.com/Mikeyphw/skybind/actions/runs/40120472501) confirmed both hosted app/test APK compilations but rejected the newly checked AndroidX receiver `android:protectionLevel` compiled integer type. The exact source-bound parser follow-up is documented in `NATIVE_05_ANDROIDX_AAPT_PROTECTION_TYPE_20261024.md`: the flag/enum `aapt` encoding (`0x11`) is recognized only for protectionLevel and must equal the signature-only value `2`. Unknown values, extra flags, new permissions and signer/version drift remain forbidden. This is **source-only remediation** until a new live GitHub workflow publishes the verified pair; APK installation, device instrumentation and owner approval remain open.
