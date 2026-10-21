# R1 handoff: read-only operation subset issuance fix

**Observed on Android 2026-10-21:** Gateway `R1_HANDOFF_DIAGNOSTICS` reported `offer_pending=true`, `attempts=4`, `delivered=0`, `rejections=4`, and `last_rejection=r1_handoff_issue_or_encoding_denied` after explicit `approve <live-chrootctl-PID> chrootctl GDDavys - system.capabilities 60`.

**Root cause (source inspection):** `GrantHandoff.Approve` correctly accepts a requested operation subset of the operator policy (`system.capabilities` inside five read-only ops). However `brokerissue.Issuer.IssueForPeer` previously used `operationsEqual(rule.Operations, req.Operations)` to require an identical list. This denied every one-op approved request under a five-op rule, while the handoff diagnostic intentionally masked the underlying issuance error. No evidence points to missing KernelSU elevation or SELinux permission.

**Fix:** `operationsWithinRule` requires a nonempty, duplicate-free subset of an explicitly provisioned rule; unknown and unapproved operations remain denied. The resulting grant is minted with `req.Operations` rather than the entire rule. Immutable operator policy, exact remote/prefix matching, TTL limits, independently verified process/PID, second identity verification, root-only issue channel, cryptographic token, and receipt revocation are unchanged. No fallback, credential disclosure, arbitrary root command, or SELinux weakening.

**Acceptance:** Unit tests verify one-op issuance against a five-op policy, denial for all four other permitted policy operations, multi-operation subset, denial of extra or duplicate ops, wrong remote, wrong process, revocation, existing full-list grant behavior, and original broker integration regression suite. A source-bound hosted Android arm64 gateway must be rebuilt and tested on a real device. `delivered=1` is not full end-to-end qualification; the client must successfully receive and use the one-operation token with backend read evidence.

**Scope:** Skybind only; chroot-ctl and BKX modules/APKs unchanged. Do not rerun accepted M2/M3 gates or apply manual M0–M8 checklists. This is an R1 diagnostic closure candidate, not a qualified release.
