# Skybind consumer compatibility — update BKX/chrootctl independently (ABI v1)

**Status:** Source/design contract only. **No external R1–R6 IPC broker, grants, executable shim or Restic transport is qualified or enabled by this document.** The frozen 57-operation CFS1 daemon API is unchanged.

## Core rule: do not bind authorization or compatibility to a consumer's source commit

The single Skybind daemon is the authoritative owner of remotes, proofs, jobs and events. Once the planned **R1 authenticated scoped gateway** and **R2/R3 protocol** have actually been implemented and qualified, independently deployable consumer adapters should negotiate a stable major-versioned ABI and capability set. New BKX/chrootctl application releases should upgrade only their own code/adapter, without regenerating Skybind APKs/module binaries, **as long as the already-installed gateway implements the capabilities they request**. A new, unsupported gateway feature, changed major ABI or security defect can still require an intentional Skybind update. There is no promise of arbitrary future native-rclone CLI parity.

The supplied October 20 chrootctl archive hashes are **historical identity evidence**, never allowlist entries, consent credentials, runtime version constraints or prerequisites for an unrelated Skybind build. BKX's previous source contract is likewise historical. Every independently built consumer binary can carry its own source/build digest and self-contained declaration, then run conformance against a stable API rather than against a frozen tree.

## Deployment layers / ownership

1. **Skybind core** (infrequent changes): owns privileged backend, scoped R1 peer/workload grants, revocation, versioned gateway protocol, authorization, audit, session/replay protection, read metadata, safe streams, and later opt-in immutable publication/Restic. No raw config/credentials, root shell, arbitrary executable, or public RC port is exposed.
2. **Versioned `skybind-rclone` client adapter** (independently rebuildable/distributable): speaks that negotiated protocol, maps explicitly allowlisted command/flag/env shapes to typed requests and bounded stdin/stdout, protects cancellation/exit codes, and refuses unsupported features. Can be updated independently of Skybind core if the ABI stays compatible. No transparent fall-through from a failed Skybind mutation to native rclone.
3. **BKX integration**: its native rclone and Restic remain authoritative until an opt-in R1–R5 device-qualified adapter path is installed; changing the BKX UI/internal backup workflow should not force Skybind rebuilds. R5 `serve restic --stdio` requires real duplex tests and repo isolation before any switch.
4. **chrootctl integration**: retains its sealed native rclone, private config ownership, `rclone://` normalization and two-pass integrity/immutable promotion expectations. A consumer-side adapter/config-view change is independently installable only after proving module-executable seals and root workload identity. Root UID by itself must never be interpreted as a client identity.

## ABI contract / negotiation rules

- `SKYBIND_CONSUMER_ABI_V1.json` specifies the **frozen major version and planned capabilities**. An empty `available_external_capabilities` list means **none are implemented**. Do not infer transport readiness from its existence.
- Each consumer version may publish `skybind-rclone-consumer-request-v1` declaration with `consumer`, `abi_major`, exact required operations and capabilities, `native_rclone_fallback=true`, `implicit_credential_export=false`. A declaration is a **request**, not an identity credential, access grant, runtime handshake or proof of implemented functionality.
- The external broker will eventually answer authenticated `capabilities` with supported operations and security scope; reject unknown ABI major, unsupported commands/flags, expired/revoked grant, missing scope and altered peer identity. Minor-version additions must remain additive and fail closed.
- R0 standalone checker `python3 -B scripts/dev/android/m3_consumer_contract_gate.py --consumer-declaration /path/to/consumer-request.json` validates declarations against the currently documented capabilities, but cannot make an absent R1 gateway exist. `BLOCKED_CAPABILITY_NOT_IMPLEMENTED` is a correct result for today's BKX/chrootctl provider requests.
- `--chrootctl-source /path/to/source` is an optional source syntax survey. Hash differences are *reported*, not rejected. `--strict-reference-sha` is a **separate historical audit** that deliberately rejects modifications; never use it as an ordinary compatibility/CI upgrade gate. Source refactors that move files should use a separately maintained declaration and eventual runtime conformance suite, not require old file paths.

## Stable conformance suite, decoupled from rebuilds

On **each consumer update**, run its independent contract/declaration check and later the actual R1+ process identity/grant denial tests, R2 metadata/parsing parity, R3 test-owned streaming/cancel/hash tests and R4/R5 specialized destructive/Restic gates only when those capabilities exist. Record consumer executable/build hash, Skybind daemon/adapter version, ABI/capabilities, actual UID/SELinux/workload identity, grant revision, binary/fixture hashes and exact individual PASS/BLOCKED/FAIL receipts. Preserve previous releases' receipts; do not rerun already-proven Skybind APK lanes merely because a BKX UI or chrootctl component changed.

Run compatibility testing against installed Skybind and the changed consumer adapter. Rebuild **Skybind only** when actual gateway behavior/ABI/security changes. Rebuild **BKX/chrootctl only** when their own application/adapter changes. Keep unqualified consumers on existing native rclone; never copy Skybind secrets or automatically migrate BKX Restic repositories/chrootctl archives.
