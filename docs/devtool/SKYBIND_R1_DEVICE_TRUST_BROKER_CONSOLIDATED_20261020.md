# Skybind R1 — consolidated trusted consumer foundation (source-bound)

**Status: SOURCE_IMPLEMENTED / SOURCE_VALIDATED, external runtime NOT_ACTIVATED, consumer device attestation NOT_QUALIFIED, no external provider or release qualification.**

## Preserved device evidence

- M3 real daemon job preview: GitHub run `39472233849`, source `af35406346680e2a813811127a88f07cee381053`, PASS narrow preview-only.
- M3 disposable CHECK and session-owned cancellation: run `39491360742`, source `d00f222a79c117fb57909df6dc1d02fa60e574bc`, PASS independently.
- M3 local disposable COPY SHA-256/reconnect/terminal: run `39506914420`, source `bb51363442ca5db139b37970dd67318df2914971`, PASS independently.
- `m3_evidence_reconcile.py` reported `PASS_FOUR_INDEPENDENT_M3_SCOPES`, `missing_scopes=[]`, `whole_m3_qualified=false`, `external_provider_qualified=false`, `release_qualified=false`. Historic rejected or unselected summaries are preserved, not overwritten.

## Installed consumer facts (observation, NOT attestation)

- BKX Android package `com.mikeyphw.bkx.android`, reported version 1.0.0, PM UID 10327; no process was observed. Neither package-signer authorization nor process SELinux was established.
- chrootctl Magisk/KernelSU module `chrootctl` version 1.3.7/code 22, `/data/adb/modules/chrootctl`. The root-owned installed runtime `/runtime/arm64-v8a/chrootctl` and package manifest were observed, SHA-256 `6280207bb5cc0abd95d9e13204e814b012a25b7ead9003f0ae9e00fed8e490f5` and `843f470dad66d65d15e7ff0f8178b7d363703f97e46f80966ddad65344c221d4`. This is discovery provenance, **not** a global whitelist or automatic approval. No chrootctl process was observed.

## Implemented source scope in this overlay

1. `brokeridentity.PlatformPackageAttestor`: requires an **authenticated** Android PackageManager authority, one exact installed package for the UID, one installed APK contents signer, independently approved signer certificate SHA-256, and correct current Android user. The signing digest must never arrive from untrusted client JSON. Any missing authority, changed package ownership, shared UID, or signer rotation fails closed. A newer BKX app version is not a hard-coded Skybind build dependency.
2. `R1PackageManagerAuthority.kt` and its Android instrumentation source: actual Android `PackageManager.getPackagesForUid`, `GET_SIGNING_CERTIFICATES`, user/UID and contents-signer SHA-256 checks. **The secure trusted Android-to-Go authority channel is not yet connected.** A standalone Kotlin platform check or UI JSON claim is *not* a production Go attestor.
3. `brokeridentity.InstalledModuleAttestor`: inspect kernel `/proc/PID/exe`, verify it points to `/data/adb/modules/chrootctl/runtime/arm64-v8a/chrootctl`, compare the in-flight executable inode/content to a root-owned regular file and manifest entry, enforce expected modes, and compare the manifest hash to an independently approved operator pin. `RootVerifier` independently checks UID 0, SELinux and PID start ticks across verification. New module versions need explicit reapproval of their new seal, not a Skybind rebuild. No automatic seal acquisition from the module's own file.
4. `brokeridentity.ConsumerVerifier`: mutually exclusive app-UID and chrootctl-root identity routes. A root UID alone cannot grant remote access; a BKX-like package name cannot grant remote access.
5. `brokeripc.ConsumerSocket`: an **explicitly activated** separate Unix socket with root-private parent, root:BKX-UID 0710 search directory and 0660 socket, `SO_PEERCRED` identity, mandatory grant store/verifier/backend, bounded request size/deadline/concurrent handlers, default deny, revocation. Does not accept arbitrary shell, raw remote credentials, arbitrary rclone execution or mutation. Tests prove denied-by-default, positive isolated read-only and immediate revoke.
6. Devtool: the `r1-device-trust-source` composite source DAG adds platform/manifest negative tests, Go broker tests and source-only activation denial checks. GitHub source workflow adds the same source validation. **Only hosted GitHub Actions may compile Skybind APKs**; the Android-side Kotlin source requires a new hosted APK compilation to prove it builds.

## Actual qualification boundaries

The Go `PackageAuthority` interface **requires a trusted Android platform bridge** to connect package signature results to a Go process; no such authenticated bridge is yet attached to the production daemon. The new `ConsumerSocket` is **not started in `cmd/skybind/main.go`**; its `Start()` requires explicit trusted component configuration and is constrained to a verified canonical socket path. The independent operator grant/attestation lifecycle, measured BKX process SELinux and active chrootctl workload attestation, real-app device denials/revocations and R2 read-only metadata backend are next. The source will **not falsely advertise** available external capabilities or issue tokens.

## No rebuild-on-consumer-update policy

- Neither the module manifest hashes nor the BKX version/source SHA are hardwired as access grants. For a changed signer/module seal, an independently approved operator security pin and grant revision must rotate; the installed Skybind binary does not need replacing if its R1 protocol still meets the consumer's capabilities.
- Consumer adapters evolve independently with the stable major-version ABI and fail closed when unsupported. Native rclone remains the existing BKX/chrootctl implementation; no automatic migration, credential export, Restic writes or silent fallback.

## Operator workflow

```sh
cd ~/Code/skybind
./devtoolw r1-device-trust-source
# Android Kotlin compilation: GitHub workflow ONLY, from pushed source.
git push origin main
gh workflow run skybind-android-apks.yml -R Mikeyphw/skybind --ref main
```

The source DAG never creates a root broker socket or runs device mutation. Do not configure an external listener simply because source validation passes. After the authenticated platform authority is connected and installed consumer processes can be measured, implement a *separately qualified* opt-in device lane for peer identity, readonly scoped query, out-of-scope denial, token revocation, PID reuse, changed package signer, changed module seal and foreign root client. Record actual UID/SELinux, approved signer/seal revisions and installed ELF/APK hashes in the resulting device receipt. Preserve all original G01–G08/CFS1 gates and historical source/device provenance without promoting release qualification.
