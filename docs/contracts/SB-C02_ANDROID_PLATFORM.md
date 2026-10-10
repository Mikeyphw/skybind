# SB-C02 — Android namespace + root-manager source contract

**Qualification:** SOURCE_IMPLEMENTED_NOT_PROMOTED. Do not infer device mount visibility, supported manager versions or real application access from Go/fixture passes. SB-G01/G02/G03/G04 remain separately blocked or unqualified.

## O15: Read-only evidence

- Bound scan: max 4,096 PIDs and 512 namespaces; preserve `Complete=false` on failures. Gather namespace symlinks, UID/user, comm and mountinfo, classify protected/mixed namespaces.
- Exact target visibility and Android aliases are different. Group-by-namespace, not arbitrary PID. User 0 and work-profile UID/user mapping are distinct.
- Allowed query consumes a mount name only; the source must be currently proved Skybind-owned FUSE with matching PID/start-time/executable/mount ID.

## O16: Targeted preview/apply

- `namespace.preview` takes a mount name and *explicit* namespace IDs observed during inspect; returns a single-spend short-lived proof over source, member set, target, namespace IDs and signature.
- Only app-only groups, complete scanning, exact target unoccupied, source unchanged. Zygote, USAP, MediaProvider, ExternalStorage, service, unknown and mixed classes always deny.
- The re-executed worker pins source and namespace FDs, enters mount namespace on a disposable locked thread, checks the destination, binds and confirms mountinfo signature. Unknown/unsupported kernel conditions fail closed.
- Ownership journaling precedes a bind; completed records persist individually. On mid-transaction failure, attempt reverse, owned-only rollback. A failed compensation leaves `attention` and prevents teardown.

## O17: Rollback/reconcile

- Proof-protected rollback requires the exact recorded namespace, source, destination, and observed mount ID; no foreign detach.
- Reconciliation after interruption never silently broadens the bind set or infers successful app visibility. Unknown/churned ownership becomes `attention` and blocks normal mount teardown.

## O18: Manager hooks

- The module uses one fixed Skybind binary and one immutable packaged upstream rclone/helper layout. Manager detection is capability-based and ambiguous evidence never grants trust.
- `service.sh` starts one daemon (native lock prevents duplicates); Action is read-only; early boot does not mutate mount namespaces. Installer checks known package paths and file identities, without downloading executables.

## O19: Uninstall/purge

- Normal module uninstall calls `uninstall-stop`, verifies namespace ledgers and owned mount identity, and **does not** delete `/data/adb/skybind`.
- Explicit purge uses `purge-preview` followed by root-only `purge-state` with a short-lived single-spend token and exact confirmation phrase. Daemon/mount/namespace activity blocks purge.
- Source tests cannot replace device proof that uninstall, real mounts and app visibility work together.

## Deliberate device constraints

Some Android builds restrict `/proc` namespace inspection, deny `setns`, or virtualize filesystem mountpoints. These must report unavailable/blocked; no fallback to shared protected namespaces, PID-only ownership, or blanket lazy detach is permitted. Normal-app read/write and manager/version coverage require later signed device evidence.
