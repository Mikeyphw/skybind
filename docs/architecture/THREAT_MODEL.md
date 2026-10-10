# Skybind foundation threat model (SB-O01)

Scope is the greenfield product. The embedded original WebUI reference is a quarantined, read-only comparison fixture, **not shipped**. No installed dynamic-runtime or historical migration behavior is in scope.

| Boundary | Threat | Mandatory invariant | Owning planned overlay |
|---|---|---|---|
| Root-private state | Non-root user reads credentials | Root-owned 0700 directories; 0600 files; no symlink traversal | SB-O03 |
| Configuration | Stale preview changes live state | Revisioned preview/proof and atomic commit | SB-O09 |
| Process/mount control | PID reused; unowned mount removed | PID+start-time and mount identity, no unowned unmount | SB-O10 |
| Android namespace | App/system namespace harmed by bind | Inspect topology; protected-process deny; rollback, exact-path proof | SB-O15–SB-O19 |
| Filesystem cleanup | Cache purge follows a link | No-follow ownership checks, bounded destructive scope | SB-O14 |
| Background jobs | Sync silently destroys data | Typed copy/sync/check plus per-revision destructive proof | SB-O20–SB-O22 |
| Privileged web bridge | Browser injects command, CSRF | Typed allowlist, Origin/Host checking, one-use bootstrap, session | SB-O27–SB-O28 |
| RC telemetry | Local RC exposed to other apps | Per-mount authenticated loopback, bounded allowlisted metrics | SB-O22 |
| rclone secrets | Password appears in logs/UI | stdin-only secret entry, redaction, root-private obscured storage | SB-O23–SB-O24 |
| Packaged binary | Runtime substitution/PATH hijack | Build-time selection; single canonical pinned arm64 binary | SB-O04–SB-O05 |
| Devtool overlay | Stale base/clobber or forged PASS | Schema-v2 inventories, source hashes, fail-closed validation | SB-O02; all gates |
| Device evidence | Root-shell check treated as app visibility | Ordinary non-root Android app proves path read/write | SB-G04, SB-G08 |

Evidence labels: `SOURCE_TEST_PASS` is not `DEVICE_QUALIFIED`; screenshot baseline is pending; a missing device blocks dependent release qualification rather than being marked pass.
