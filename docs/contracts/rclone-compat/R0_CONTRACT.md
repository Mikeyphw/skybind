# R0 — Skybind shared rclone provider compatibility baseline

**Status: source-only, NOT IMPLEMENTED.** Based on Skybind `cf4d9fc8445b3c90690e0fee3e76235d7913cbe7` and BKX snapshot `bkx-20261016-170717-423795.tar.gz`.

## Purpose and non-goals

Make Skybind the authority for managed rclone remotes. BKX and later apps may use a **scoped, rclone-compatible client executable**; no BKX backup/Restic rewrite is intended. R0 does **not** implement `skybind-rclone`, a privileged broker, any remote access, or `serve restic --stdio`. The Python harness only classifies syntax and explicitly refuses execution; its successful tests are **not** proof of upstream rclone parity or Android qualification.

## BKX's concrete invocations

`internal/rcloneops/runtime.go`: `version`, optional `--config`, executable probe `rclone v...`, readable `BKX_RCLONE_CONFIG` for remote-name preflight. `list.go`: `lsjson` with `--max-depth 1`, `--stat`, `--no-mimetype`. `transfer.go`: `size --json`, `copy` / `copyto` / `sync`, JSON progress logging flags, retries, `--ignore-existing`, bounded `--max-delete`, and `check --download [--one-way]`. `remote_files.go`: `copyto --immutable`, `deletefile`, `lsjson --recursive --files-only`. `mkdir.go`: `mkdir`. `resticops/restic.go`: Restic's `-o rclone.program=...` with `rclone:` repository, whose executable must handle `serve restic --stdio` and full-duplex protocol; this is **not** replaceable by a simple one-shot RPC.

`listremotes` is an **expected future interoperability feature**, not a directly observed BKX source call. Treat `--config` as a BKX invocation requirement, not a permission to read Skybind's actual privileged config. BKX's current remote-name preflight needs a scoped non-secret catalog or a small, intentional BKX integration adjustment. Never fabricate a credential-bearing rclone.conf.

## Proposed capability ladder (ALL DEFERRED)

| Tier | Initial commands | Required next gates |
|---|---|---|
| READ_ONLY | `version`, `lsjson`, `size`, `check`; proposed `listremotes` | R1 authenticated cross-UID broker + R2 JSON/exit/output parity |
| SAFE_TRANSFER | `copy` with policy-backed no-overwrite | R3 test-owned data, lifecycle, cancellation and durable jobs |
| GUARDED_MUTATION | `mkdir`, `copyto` | R3/R4 scoped write and overwrite proofs |
| DESTRUCTIVE | `sync`, `deletefile` | R4 deletion/race/rollback safety and per-client opt-in |
| RESTIC_STREAM | `serve restic --stdio` | R5 full-duplex protocol and repository integrity |

These classifications are design categories **not permissions**. No command currently executes through the new interface. See `R0_BKX_CLI_MATRIX.json` for machine-readable arity, flags, source references and nonqualification.

## Required execution and security contract for R1+

1. A per-client, cryptographically or OS-verifiably bound session: verified app UID, package signing identity and grant; exact Android SELinux domain/exec-context investigation. Caller-supplied package names are not identity.
2. Per-request remote and path-prefix grants, revision and expiry, remote root containment, explicit SAF/local-root authorization; never allow raw privileged files, `rclone rc`, raw `--config` override, proxy env overrides or unrestricted command passthrough.
3. A request may contain **zero or more** rclone-compatible flags but every flag and position must be allowlisted with semantic validation. Unknown flags and unqualified options are rejected before effects, not sent to privileged native rclone.
4. Native-looking stdout/stderr, exit status, JSON content, SIGTERM/cancel, partial results and progress are claimed only after source-bound golden tests against actual upstream rclone; no fake success on unsupported features.
5. A stdout stream for ordinary CLI commands is different from **bidirectional** Restic `serve restic --stdio`. Dedicated repository namespaces, locks, atomic-write/durability constraints, prune/delete permissions, transport backpressure and process death are needed for R5.
6. Any ambiguous write, restart or transport timeout fails closed; never silently fall back to BKX's independent rclone after a Skybind error. Maintain the authoritative Skybind daemon journal.
7. Keep CFS1 frozen catalog untouched: all new operations belong to an opt-in, versioned provider extension. Existing mount/offline journal and test-owned V9 fixture stay untouched.

## Evidence and caveats

- `R0_BKX_SOURCE_SHA256.json` pins the BKX files inspected for this inventory; `R0_BKX_CLI_MATRIX.json` pins the two source snapshot identities.
- `scripts/dev/provider/rclone_compat_r0.py` is **only** a safe offline syntax-check harness, never an rclone runner or authorization mechanism. Its result for a correctly shaped request is still `DECLARED_NOT_IMPLEMENTED`.
- A distinct UI instrumentation APK remains planned for the native Skybind Android app. It cannot alone prove root daemon and cross-app transport survival; Devtool must coordinate actual process death and on-device state.
- R0 exit: source inventory, fail-closed parser tests, threat model and R1 interface decisions. R1 implementation requires explicit transport/caller identity decision and device tests.

## Deferred device gates and prior evidence

Historical backend A1–B3: 14 PASS (as previously recorded). Passive reboot: 5 PASS, 3 BLOCKED. V8 WebView: 6 collector-level PASS, 4 BLOCKED. V9 synthetic callback recovery: 1 PASS in earlier run; three physical interaction cases BLOCKED, while later independent screenshots corroborate visible navigation. No earlier result is retested or upgraded here. Installed ELF provenance and formal release qualification still open.
