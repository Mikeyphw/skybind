# Skybind B1-C3 — read-only UID and SELinux observation

## Prerequisites

B1-C1/B1-C2 were applied; the successful hosted pipeline `be9ee025156643fe9a5c21d577dd0d2f` was H4-attested; both installed APKs matched the attested source-bound archive; both B1-C instrumentation cases passed on device.

## Run

```sh
cd ~/Code/skybind
python3 scripts/dev/android/r1_b1c3_identity.py
# Or use the native Devtool target: ./devtoolw r1-device-identity-survey
```

The command re-verifies the H4 receipt, archive and installed exact app/instrumentation APK byte hashes. It queries **both** Android `pm` and `cmd package` for user-0 package/UID mappings, requires exact agreement, unique non-system UIDs for the app and test package, checks SELinux `Enforcing`, and records a new write-once JSON receipt at `build/evidence/android/b1c3/`. It never changes the device, dispatches GitHub, or enables the broker.

Success state: `PASS_B1C3_UID_OBSERVATION_NOT_BROKER_AUTH`. On malformed, missing, shared-UID, mismatched package mapping, APK drift, or SELinux non-enforcement, it fails closed with `BLOCKED`. The diagnostic state is not a release gate pass.

## Strict limitation

Both `pm` and `cmd package` run through ADB shell and **are observational tools**, not authenticated package attestation of a live cross-UID Go socket peer. A native privileged Android Platform/Binder identity service and its trusted transport are not implemented. Never use a survey receipt as `brokeridentity.PackageAttestor`, as a grant authority, or as evidence that the root broker may serve external clients. The original two Android instrumentation PASS cases are preserved.

## Next engineering gates

1. Design a privileged trusted Android Binder identity resolver with call-site verified UID, certificate pinning and package-owner isolation, and mutually authenticated broker linkage.
2. Bind that resolver to `brokeridentity.AndroidVerifier` using OS-proven UID/PID start identity; forbid replay, PID reuse, and caller-owned identity fields.
3. Build additional Android tests on a new source commit via GitHub Actions only; instrument positive and negative caller/UID/signature cases and independent denial tests before any listener is enabled.
4. Keep explicit grant issuance and review of SELinux/domain policy separate; no broad capability escalation.
