# Skybind personal release — active policy

As of the personal-release migration, Skybind uses `SKYBIND_PERSONAL_V1`, not
external CFS1 attestation. The canonical CLI `scripts/dev/seal/sb_cfs1.py`
reads the local evidence index and owner decision; it never creates a signing
key or requires a third-party reviewer.

A personal release requires a clean source checkout, unchanged typed API
catalog, reviewed Q16/Q17 raw reports, recorded R1 and M2/M3 evidence,
verified candidate ZIP (including member hashes, ARM64 executables, provider
provenance and deterministic package layout), and explicit owner acceptance
on the selected device/root manager. Manual UI/device checks are **owner-reported**;
they are never presented as automated test passes.

The authoritative result is `PERSONAL_RELEASE_APPROVED` scoped to exactly the
selected candidate SHA-256 and manager. Changes in source or evidence invalidate
that approval. Other root managers and devices remain untested unless separately
qualified. Legacy independent-CFS1 statuses and signatures are retired from the
active personal workflow.

See `docs/qualification/SKYBIND_PERSONAL_RELEASE.md`.
