# SB-G01 — Foundation and supply-chain gate definition

**Present status: BLOCKED / NOT SEALED**. This is a real independent Devtool
milestone gate implementation, not an already-issued qualification.

`python3 scripts/dev/gates/sb_g01.py --check` returns exit status **3** if
external source pins, independently authenticated real-provider outputs and
complete Devtool evidence are missing. Its targeted *self-tests* confirm this
negative behavior and may pass while the gate itself remains blocked.

The gate requires SB-O01..SB-O05 and independently built, byte-identical
NewFuture/bclone artifacts, SHA-256 and official-source provenance, unchanged
NewFuture FUSE helpers, and a trusted release/pin record. Human/source trust
review and exact Devtool apply receipts remain mandatory. The gate can claim
SOURCE_BUILD_PASS **only**; it never claims real Android app visibility, boot,
FUSE usability, original WebUI visual parity or final seal.

Evidence producer/attestation flows will be expanded when real pinned upstream
archives and tools become available. Don't fill missing evidence with tests'
synthetic ARM64 ELF fixtures.
