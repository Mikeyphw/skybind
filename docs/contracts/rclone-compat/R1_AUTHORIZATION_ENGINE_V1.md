# R1 consumer gateway policy foundation — non-network, source-only

**Status: R1 policy engine implemented and tested; external transport NOT_IMPLEMENTED; real process/OS identity and consumer runtime NOT_DEVICE_QUALIFIED.** This document deliberately does not grant access or claim rclone compatibility. Existing source commit `bb51363442ca5db139b37970dd67318df2914971` is the preimage of this next consolidated overlay; M3 real COPY qualification is recorded separately.

## Source-level implementation

Skybind already has a bounded `internal/brokergrant` grant store, `internal/brokeripc` SO_PEERCRED request handler, `internal/brokeridentity.AndroidVerifier`, and `internal/brokerissue` operator-approved issuance core. This overlay **extends those components rather than introducing a competing authorization engine**. The existing stack supplies deny-by-default scoped read-only grants, 256-bit random tokens, SHA-256 token digests, revocation and per-operation authorization. `internal/brokeridentity.RootVerifier` adds a separate root-module identity policy for chrootctl: verify `/proc/PID/stat` starttime, four root UID fields, `/proc/PID/attr/current` SELinux label, and a *trusted independent module/process attestor* before and after observing the same process incarnation. No verified module attestor exists on the installed device yet; wiring it is a separate gate.

The principal's `AttestedIdentity` must be created **only from independently authenticated OS/process evidence**, not JSON supplied by a consumer. The BKX path is now also bound to a separately approved measured SELinux context, in addition to its existing UID, package-signer and process-incarnation attestor. chrootctl requires sealed module/workload attestation **and** measured SELinux context; UID 0 alone is insufficient. Process identity is separately scoped to its lifetime, while future updated module binaries may be approved by an independently updated attestor/grant without a full Skybind source rebuild. An updated consumer version is not pinned to its historical source hash: renewed attestation/grant rotation can occur without rebuilding Skybind, provided the installed stable gateway supports the requested ABI/capabilities. Self-declared identity strings are never a grant.

## Not present / next R1 requirements

- No Unix-socket listener, app-exported Binder API, TCP/loopback listener, native-rclone executable shim, remote config export, rclone process runner, credential API, streamed file data, installed module change or APK change.
- The **published** `SKYBIND_CONSUMER_ABI_V1.json` still advertises `available_external_capabilities: []` and `external_transport_status: NOT_IMPLEMENTED`. A source-only unit test simulating a metadata capability does not activate it for BKX or chrootctl. Their own native rclone paths remain unchanged.
- Next R1 transport must securely obtain Android peer UID, package signature and SELinux domain (and separately establish chrootctl root-workload identity). Validate actual BKX SELinux/process executable restrictions and module-seal behavior on the target device before any socket/IPC exposure. Fallback must not silently change endpoints or rerun ambiguous writes.
- Next R2 metadata operations require version/listremotes/lsjson/size parity and credential-free scoped remote views. R3 streaming, R4 immutable moves and R5 Restic stdio remain blocked pending their own safety gates. No destructive sync is enabled by R1.

## Independently updated consumer compatibility

Consumers update their *adapter/declaration* independently. Change in consumer source or APK SHA alone does not require rebuilding Skybind. Negotiate ABI major and supported capabilities against the installed server; deny unsupported requests. Issue a new attestation/grant when security-relevant workload identity changes. Installing the current R1 package does not make a consumer compatible without the missing broker and device acceptance.

## M3 evidence reconciliation

`scripts/dev/android/m3_evidence_reconcile.py` reads authentic local exact-run device summary JSON files and their referenced native lane receipts. It independently checks source SHA, GitHub run/artifact IDs, signer and installed pair flags, scopes, and the COPY content-hash/sentinel evidence. It never runs an Android test. Historic preview, check, cancel and copy can each be from different GitHub builds. **An aggregate of four narrowly passing scopes is not a full M3/product release qualification.**

On the Android/Termux device after applying this source overlay:

```bash
python3 -B scripts/dev/android/m3_evidence_reconcile.py \
  --summary-root "$HOME/.local/state/skybind/ci-artifacts-device" \
  --native-root "$HOME/.local/state/skybind/native-m2-live"
```

No `--install`, no `$RUN_ID` change and no `--serial` selection is necessary because this is file-only. Device qualifications remain anchored to their **original** signed APK bytes/commits; no new device pass follows from the script itself.

## Source and Devtool qualification

`./devtoolw r1-consumer-foundation-source` verifies the existing R1 broker policy plus the newly added root-module verifier, Go tests, consumer R0 declaration denials, scope/receipt negative cases, prior M3 regression and GitHub-only Android build restriction in one six-node DAG. Hosted `skybind-source.yml` also performs the R1 source checks. No M2/M3 lanes rerun and no module/consumer source pinned to unrelated commits.
