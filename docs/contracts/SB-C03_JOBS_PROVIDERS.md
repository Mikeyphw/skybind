# SB-C03 — Jobs, isolated RC, remote browsing, crypt

Source-level implementation obligations: SB-O20, O21, O22, O23 and O24. This
source record does not qualify cloud credentials, physical Android devices,
installed rclone artifacts or SB-G03/G05 release gates.

## Jobs

- A revisioned, bounded 128-job registry and proof-protected edits; server owns
  next-run times and last-run identity.
- Copy, sync and check use fixed rclone command forms, never arbitrary flags,
  shell commands or local-path endpoints. Sync is visibly destructive.
- Manual runs require a one-use subject/revision/digest proof. Scheduled runs
  require an applied configuration; persist run claim before invoking rclone.
- Restart marks stranded jobs INTERRUPTED. A completed remote transfer is only
  claimed after its executor exits successfully. Unknown network facts are not
  silently assumed safe, except explicitly configured offline-allowed policy.
- Cancellation uses the canonical operation.cancel route for active owned runs.
- Progress comes from bounded numeric rclone JSON stats only; raw stderr,
  credentials, remotes and paths never appear in progress output.

## Providers and crypt

- Discover remote name/type with private config read, never config/dump/RC proxy.
- Browse only named remotes through fixed lsjson with path validation, response
  caps, strict JSON, 30s timeout and a 500-entry limit.
- Password enters the native backend only through authenticated RPC; rclone
  obscure reads it on STDIN, not argv; only the obscured password is stored
  in 0600 root-private state. Obscuring is NOT cryptographic protection.
- Creating a crypt wrapper requires proof, a configured password, a previously
  existing non-crypt remote, and atomically publishes a validated stanza.
- Credential-free recovery-status explains that plaintext recovery is not
  provided and advises users to retain their password separately.

## Authenticated RC

- The mount engine receives only internally generated --rc options.
- Each mount gets a randomized 256-bit credential and a loopback address.
  htpasswd contains only a hash, not the plaintext password or CLI argv value.
- RC access is restricted to core/stats and vfs/stats; only allowlisted numeric
  statistics can be emitted. Unowned mounts and missing volatile sessions fail
  closed; no general RC endpoint can be invoked from the public API.

## Source/device evidence

Devtool apply automatically runs package tests under umask 022 and 077,
compiles Android/arm64, executes supported-host race tests, verifies the
57-operation catalog and C03 wiring, and checks the existing feature and
original-overlay obligation inventory. Real rclone network transfer, crypt
roundtrip and Android process namespace qualification are separate gated tasks.

**SB-G01/G02 remain BLOCKED. SB-G03/G05 and the final seal are not issued.**
