# Skybind R1 — local handoff rejection diagnostics (source-bound)

**Scope:** operator visibility only. This patch does not change any authorization predicate, TTL, broker policy, R1 socket name, client protocol or token transport. No consumer grants are issued by diagnostic commands. No Android installation, M2/M3 rerun or release qualification.

The interactive root gateway command `diagnostics` reports `R1_HANDOFF_DIAGNOSTICS {…}`. Fields: `offer_pending`, `offer_seconds_left`, `attempts`, `delivered`, `rejections`, `last_rejection`, and `rejection_counts`. Counts reset after each accepted `approve` command, and the snapshot holds only fixed rejection codes. It never includes bearer tokens, receipt IDs, PID, scopes, signer material, sensitive file paths, or arbitrary errors from untrusted clients. The client-facing protocol remains unchanged.

## Interpretation

- `offer_pending=true`, `attempts=0`: the approved offer has not been contacted since approval.
- `r1_handoff_wrong_process`: a connecting client had a different `SO_PEERCRED` triple (PID/UID/GID). Do not approve a wrapper or parent PID.
- `r1_handoff_identity_changed`: the pinned executable/process verification did not match on reinspection.
- `r1_handoff_approval_expired`: the 30-second one-time offer timed out before a valid connection.
- `r1_handoff_issue_or_encoding_denied`: server re-verification/issuance or encoding returned an error; no raw error is disclosed.
- `delivered>0`: the grant packet was written to a verified client socket. It is **not** proof of a successful metadata read.
- An empty `receipts` listing is not conclusive after expiration or revocation; use immediate `diagnostics` output within the client's 120-second lifetime.

Run `diagnostics` immediately following the exact-PID `approve` command and again after the client exits. Never change KernelSU / SELinux to permissive to troubleshoot. Restart the root gateway only after a fresh hosted source-bound diagnostic build and operator review.

R1 device-grant, Android SELinux socket and BKX adapter qualification remain pending until genuine live pass/deny/revoke receipts exist.
