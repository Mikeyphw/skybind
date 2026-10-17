# B1-A — Read-only broker transport foundation (Devtool native overlay)

- **Prior Termux checkpoint:** W3 isolated full regression reported PASS by operator. Record as user-reported until complete source-bound receipt supplied; previous monolithic `WaitDelay` is retained as nonblocking tool/runtime debt.
- **Added:** `internal/brokeripc` performs one bounded versioned typed JSON exchange on an *already accepted* Unix connection. It derives PID/UID/GID from kernel `SO_PEERCRED`; a required independently trusted process verifier supplies `ProcessKey`. It checks the existing `brokergrant` authorization before invoking a typed read-only handler.
- **Fail closed:** absent verifier/grant store/handler, malformed or excess-length input, extra fields, wrong version, PID/UID disagreement, missing/revoked/expired token, non-whitelisted operation, remote/prefix mismatch, backend error and oversized/invalid response.
- **Not yet implemented:** Android package-signing identity resolver, controlled administrative grant issuance, live external broker listener, typed rclone implementations, APK compilation, APK provenance or real device integration. This source package opens **no** listener and creates **no** grants on its own.
- **Devtool:** `r1-transport-source` composes independent BKX/chrootctl, grant-policy, transport and hosted-build-policy checks. `r1-full-regression` composes that with the existing W3 isolated all-package Go test job; it never silently substitutes a fast gate for full coverage. Native GoRunner's monolithic path remains diagnostic only.
- **Android:** Both app and test APKs must be built on GitHub Actions. All new tests are Go/Python source checks; no local Android Gradle invocation is included.
- **Safety:** No real device mutations, cloud calls, root operations or destructive file operations. Historical evidence is not rewritten.

## Apply and test

```sh
cd ~/Code/skybind
devtool -r "$PWD" overlay check ~/storage/downloads/SKYBIND_B1A_BROKER_TRANSPORT_DEVTOOL_OVERLAY_20261017.zip
devtool -r "$PWD" apply-overlay ~/storage/downloads/SKYBIND_B1A_BROKER_TRANSPORT_DEVTOOL_OVERLAY_20261017.zip
# Use the newly installed source DAG for execution evidence:
devtool -r "$PWD" invoke r1-transport-source --target skybind_release
devtool -r "$PWD" invoke r1-full-regression --target skybind_release
```

The Devtool-native overlay uses checksum-verified file inventory, atomic transactions, conflict rejection and a scoped single commit. On the inspected Devtool build, apply-time nested workflow validation is unreliable; automatic validation is explicitly disabled. **Immediately run the separate Devtool `r1-transport-source` workflow** (and full regression for milestone acceptance); neither a successful apply nor an automatic commit is a passing validation receipt. Apply uses source-digest conflict detection, atomic rollback, and Devtool's transaction receipts. **Do not reapply W3**: this overlay expects W3 files already present.
