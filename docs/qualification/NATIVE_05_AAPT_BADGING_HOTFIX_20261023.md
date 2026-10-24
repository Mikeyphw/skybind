# Skybind NATIVE-05 — hosted APK metadata verifier hotfix

**Source baseline:** GitHub clean commit `9906965436e1899a41a151f1e3ab4c74079173b8`, Git tree `c9e27642533bee59519e14dd91e741e5d02b2603`.

**Evidence:** workflow run [40054250297](https://github.com/Mikeyphw/skybind/actions/runs/40054250297), `Build personal non-debuggable APK + matching androidTest APK` PASS; `Verify exact personal pair` FAIL: `COMPILED_PACKAGE_IDENTITY_UNAVAILABLE`; artifact publication SKIPPED.

The compiled package metadata parser required nonempty `versionName`. The exact `aapt` metadata was not logged or retained, but AndroidTest may legitimately emit `versionName=''` or omit it. This narrow repair accepts that variant while preserving all release-app version, signer, package, source, SDK, permissions and instrumentation-target checks. Missing package name, versionCode, duplicated attributes and malformed identities still fail closed.

## Promise checklist

| Promise | Source state | Evidence | Outstanding live gate |
|---|---|---|---|
| Personal APK and test APK compile | Already passed | Workflow 40054250297 | Repeat for new source SHA |
| Parse generated test metadata | Source repaired | `test_aapt_androidtest_empty_or_missing_version_name_is_valid`, mocked full pair | GitHub rerun |
| Reject absent/ambiguous package/versionCode | Source implemented | malformed fixtures and negative assertions | GitHub rerun |
| Enforce exact personal-app version | Unchanged, negative tested | `assert_pair` | Hosted verifier |
| Same APK/test signer and instrumentation target | Unchanged, negative tested | `assert_pair`, immutable manifest verification | Hosted verifier |
| Correct SDK and permission inventory | Unchanged, tested | `package_identity`, `assert_pair` | Hosted verifier |
| Immutable signed candidate ZIP artifact | Not published | run 40054250297 failed | New successful hosted run |
| Matching on-device APK, module and daemon | No device run | NATIVE-06 runner | Installed physical device |
| Instrumentation and owner approval | No device run | NATIVE-06 gates | Explicit live evidence |

Apply the source-bound Devtool overlay only on the exact clean baseline, push the resulting commit, and dispatch a **new** `skybind-personal-apk.yml` run on `main` (version code greater than installed APK). The failed run's version code `2` may be reused if it remains eligible. A rerun of the failed job would use old source and is not sufficient. Do not install, uninstall, or qualify any APK from run 40054250297; none was published.
