# API-02 — Skybind managed-features API v1 (root-local source contract)

## Merge window and boundaries

API-01 (upstream rclone and root-private Skybind config), API-02 (this **root-only** managed-feature facade), and API-03 (independently attested BKX/chrootctl consumer migration) were reviewed as an adjacent window. API-02 and API-03 must **not** merge: API-03 requires per-consumer identity and device authorization evidence; enabling cross-UID access now would bypass R1's independently attested Android PM, SELinux and root-module boundaries. The R1 broker remains unchanged and no external port/abstract socket or Binder component is activated.

## Supported root-local interface

The installed `skybind` native executable adds a **versioned, machine-readable** facade through the existing root-owned same-UID private Unix daemon socket:

```sh
su -c '/system/bin/skybind feature capabilities'
# stdin must be a single JSON object; never put proofs in argv
printf '%s\n' '{"api_version":1,"request_id":"inspect_20261026_a","arguments":{}}' \
  | su -c '/system/bin/skybind feature call mount.list --stdin'
printf '%s\n' '{"api_version":1,"request_id":"preview_20261026_a","arguments":{"name":"Demo"}}' \
  | su -c '/system/bin/skybind feature call mount.start.preview --stdin'
# For a real mount.start, supply the actual proof from preview and a fresh request_id.
# NEVER copy example proof strings into a production mutation.
```

The process must be root and the daemon must already be running. **An ordinary Android app does not automatically gain root by executing `skybind feature`.** The kernel UID check and the daemon's existing `0700` state directory, `0600` Unix socket and SO_PEERCRED check remain authoritative. On devices where `/system/bin` is not in the caller's PATH, use the absolute installed executable. No config or rclone remote is exposed through this facade.

`skybind feature capabilities` reports `api_version=1`, `protocol_version=1`, `transport=private_same_uid_unix_v1`, `authorization=root_only`, and an ordered list of feature operations with `implemented` set using the daemon's **actual registered handlers** (not a static promise). Check `implemented=true` before invoking optional features.

`skybind feature call <operation> --stdin` accepts a bounded JSON body with exactly `api_version:1`, `request_id` (1–80 ASCII alphanumeric, `_` or `-`) and object `arguments`. The executable supplies `operation` from the command line and derives its class from the allowlist; no caller can select a class or socket. Unknown/duplicate JSON fields, duplicate nested argument keys, trailing JSON, shell arguments and oversized input are rejected. No raw backend exceptions or command lines are logged by the interface. RPC responses retain protocol v1 `{schema_version,request_id,ok,result/error}` form and nonzero exit status on failure. API-02 does not rewrite the frozen 57-operation CFS1 catalog.

## Public operations

- Mounts: `mount.list`, `mount.status`, `mount.health`, `mount.start.preview`, `mount.start`, `mount.stop`, `mount.restart`, `mount.reconcile`.
- Android namespace: `namespace.inspect`, `namespace.preview`, `namespace.apply`, `namespace.rollback.preview`, `namespace.rollback`, `namespace.reconcile`.
- Operation follow-up: `operation.status`, `operation.events` (only if the event spool registered successfully).

No remote credential methods, rclone commands, file browser, raw PID controls, arbitrary paths, shell execution, application grant issuance or config writes are part of this API. Native `rclone` continues to be the proper tool for all ordinary upstream operations.

## Mutation, proof and lost-reply behavior

The facade delegates every request to Skybind's existing typed engine. `mount.start`, `namespace.apply`, and `namespace.rollback` **still require their own fresh preview/proof**; running the CLI doesn't mint bypass proofs. Mount-stop/restart/reconcile and namespace-reconcile continue to use their existing ownership, worker and policy checks. The facade never starts a second FUSE controller.

The daemon executes public calls through `feature.execute` with an internal **serialized mutation admission lock** and the existing durable journal. A repeated mutation `request_id` yields `duplicate_request_use_operation_status` without re-executing its handler. This denial is not proof that the original operation succeeded: retrieve `operation.status` using `{"id":"<original_request_id>"}` with a new query request ID and inspect the actual receipt. A status failure/unknown outcome must be resolved against device state, not automatically retried. No caller should silently replay an ambiguous write under a new ID. The lock protects API-02 calls with each other; legacy internal transports and external independently authorized programs retain their own existing contracts.

This is a **source-implemented contract only**. Tests can prove the wrapper and mock journal logic, not real Android FUSE readiness, namespace propagation, root-manager mounting, actual config conflicts, SELinux attestation, BKX/chrootctl compatibility, signed module distribution, or owner approval. All remain separate device/consumer qualification gates.

## Acceptance obligations

- Source: canonical operation-name/class parity, root-only CLI, actual daemon registration, strict JSON + duplicate denials, no shell/rclone/export operations, preview/proof and ownership delegation, durable duplicate denial, bounded event cursor, and no R1 autoactivation.
- Hosted: pinned Go CLI compile, full source CI, source-bound native module candidate and verification for a new exact commit.
- Android: root-authorized installed `skybind feature capabilities`, readonly mount.status/health/namespace.inspect, controlled disposable prefix preview+start/stop/reconcile, verified mount namespace identity, lost-response reconciliation and progress event replay, no unrelated mount changes. Separate root-manager PATH/config gate for API-01.
- Consumer: BKX and chrootctl must independently verify identity/SELinux, transport and permission decisions; there is **no** non-root feature socket or SDK authorization in API-02. API-03 must not bypass admission to use this command.
