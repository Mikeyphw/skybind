# Skybind native M1 — implementation checkpoint (not a new roadmap)

Authoritative plans: `SKYBIND_NATIVE_ANDROID_MASTER_PLAN_20261016.md` M0–M5 and `SKYBIND_UNIFIED_API_ROADMAP_20261016.md` A1–E/R0–R6; updated Devtool GitHub-only plan. This checkpoint restarts actual app product work.

## Delivered in one source-bound overlay

- Real Kotlin/Compose five-screen app with stable state/navigation and clear offline, not-authorized, connecting and degraded statuses; Home, Browser, Jobs, Activity and More.
- Read-only data model with explicit job-snapshot vs event-journal split, sequence cursor, gap flag, fail-closed cleanup of stale untrusted state and coroutine cancellation propagation.
- Production default-deny/unpaired gateway; **NO** live daemon connection, broker grants, root, guessed sockets, generic shell, privileged endpoint or credential import.
- Real test-only fixture for Compose navigation, Activity-vs-Jobs separation, Browser filtering and disabled operations; activity recreation test is not true process-death acceptance.
- Python fail-closed source gate with positive and six negative regression checks; integrated in existing grouped Devtool source runner. Build remains GitHub-only; preserve historical device pass tied to previous installed APK bytes.

## User-visible outcome

Installed *after new GitHub build and authorized device installation*: a functional navigation/control-center UI with meaningful explicit unpaired states. This does not yet manage live Skybind until security-approved M1 broker handshake is wired. New Android instrumentation APK includes five tests; none are claimed PASS on physical device until run and attested.

## Next execution block

1. Finish secure Android PackageManager/Binder to privileged daemon read-only identity bridge and revocable scope; test external unauthorized distinct-UID app; NEVER expose general root shell.
2. Wire `SkybindReadOnlyGateway` to real `system.capabilities`, `runtime.status`, `provider.remotes`, `jobs.status`, `operation.events` with schema/version and cursor verification, dispatch coroutines off main thread, timeout and stale-result guards.
3. GitHub Actions assemble app+instrumentation; Devtool Actions-06 archive/attestation; guarded install; run UI test methods with exact source+signer; validate screenshots/layout safely and persisted Activity recreation.
4. Then M2 read-only metadata Browser and mounts and M3 confirmed operations. Keep WebUI fallback and BKX/chrootctl R1–R6 independent.

**Not release qualified.** Future device-gate fixes (including Git SHA-1 validation) should be bundled with substantive broker work, not isolated hotfixes.
