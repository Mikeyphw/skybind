# SB-G02 — Typed authority and transactional configuration

**Current promotion: BLOCKED.** Installation and verification of this gate's
logic is *not* evidence of a passed milestone. `SB-G01` is independently
blocked by missing verified build provenance; `SB-G02` depends on it.

## What the gate independently verifies

- All SB-O01..SB-O09 source obligations, real overlay receipts, source commit,
  source hashes and a matching 57-operation catalog.
- Two fresh-process Devtool validation sessions at the same source commit with
  no warning, a complete negative-case matrix, and accessible run evidence.
- Real root-authoritative control-plane behavior, class/payload rejection,
  immutable operation ownership, single-use replay protection, crash
  consistency, and CLI↔daemon parity.
- Source-only assurance. Android mount namespace, real FUSE mounting, root
  manager handling, WebUI visual parity and final release are NOT attested.

Evidence schema: `build/evidence/sb_g02_source.json`. Arbitrary status strings
and test fixtures cannot promote this gate. The Devtool gate-definition job
runs the evaluator's *negative tests*, not the promotion operation. The gate
must be run independently once source dependencies and verified evidence are
available. Inability to substantiate a receipt is a blocker, never a warning.

**Exported obligations:** SB-O10 owned mount lifecycle after SB-G02; SB-G03
mount/retry/cache safety; SB-G04 Android visibility; SB-G07 original WebUI
visual/UX parity; SB-FS1 real-device and reproducible release proof.
