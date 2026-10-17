# B1-B Android identity and grant issuance — source checkpoint

Date: 2026-10-17. Base: inspected snapshot `skybind-20261017-023429-863590.tar.gz`, which **already includes B1-A**; Devtool source examined: `devtool-20261015-183913-544711.tar.gz`. This overlay contains **B1-B changes only**; do not reapply B1-A.

## Implemented

- `brokeripc`: bounded versioned Unix transport, kernel `SO_PEERCRED`, strict payload parsing, re-verification after request parsing and before authorization; **no listener is opened**.
- `brokeridentity`: `/proc/PID/stat` PID start ticks + `/proc/PID/status` four UID fields; root/shared-UID/ambiguous package attempts denied; requires explicitly provisioned platform `PackageAttestor` to validate the package and installed signing-certificate digest. Empty/unconfigured attestor fails closed; process incarnation and signing certificate are hashed into the ephemeral broker `ProcessKey`.
- `brokerissue`: only an internal issuer, requiring an exact operator-provisioned rule covering the caller process incarnation, remote, prefix, read-only operation set, and TTL. Rechecks the real peer identity before minting; token revocation is inherited from `brokergrant`.
- Kotlin `UidPackageEvidence.verify`: local-only Android PackageManager implementation checks singleton package ownership and pinned SHA-256 certificate. **A caller-supplied response from this helper is NOT sufficient for a Go broker trust decision.** It is not wired into the privileged broker.
- Devtool DAGs: `r1-identity-source` and `r1-full-regression` compose independently reusable target-local gates without local Android builds.

## Strictly pending

1. Trusted Android Binder-facing/privileged PackageManager attestation authority and authenticated handoff into the Go daemon. Until this exists, `AndroidVerifier.Packages` is unconfigured in production, all external callers denied.
2. Real BKX UID/package/signing certificate, chrootctl sealed root-module identity (currently intentionally unsupported), and source-/installed-APK-bound grant approvals.
3. Real cross-UID socket/SELinux/storage access testing on disposable remotes; no production listener is enabled and no root tunnel is exposed.
4. Hosted GitHub Actions app and separate test APK compilation, independent artifact verification, on-device instrumentation, and complete R1 acceptance.
5. R2–R6 and final roadmap qualification.

## Evidence rules

Go and Python source tests show only internal API correctness. They are not Android system attestation, external caller authentication, APK build proof, device qualification or release eligibility. No artifacts are allowed to inherit prior Go regression approval across new source hashes. Monolithic Go WaitDelay remains historical technical debt, even though the user reported the W3 isolated suite passed on Termux.

## Repo discovery caveat

The archive's `.git/config` points to `git@github.com:Mikeyphw/skybind.git`, but public/connected GitHub lookup returned 404 on 2026-10-17. Treat remote push/commit as **user-reported, not independently verified**. This overlay uses per-path source SHA-256 checks from the supplied archive, not a guessed remote commit SHA. If your actual HEAD differs, run `devtool overlay check` and resolve conflicts without forcing.

## B1-B source overlay provenance correction

The earlier combined B1-A+B1-B overlay incorrectly marked the existing B1-A broker IPC files as additions and pinned `.devtool.toml` to the pre-B1-A SHA-256 (`399e112b...`). The post-B1-A file instead hashes to `249a7553...`. The combined overlay was rejected as designed; do not override conflicts or replay it. This B1-B-only overlay pins all modified paths to the exact post-B1-A source hash, omits unchanged B1-A files, and retains preexisting W3 evidence. Independent Android identity attestation is still absent.
