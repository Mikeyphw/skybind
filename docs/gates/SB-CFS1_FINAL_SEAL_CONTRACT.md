# SB-CFS1 — Independent final release-seal verifier

**Installed artifact status:** source auditor installed, never a release approval. **Actual final release seal: NOT ISSUED.** The evaluator uses original SB-FS1 requirements and rejects source-only Devtool passes as release evidence.

## Source and gate authority

1. Verify canonical Skybind product identity, frozen Git source commit/tree, a clean worktree, original 45 obligations with 57 typed operations, and preserved original WebUI reference.
2. Evaluate every canonical SB-G01–SB-G08 *actual* gate (not gate-definition tests), with all eight expected positive statuses and their original dependency edges. The independent G03–G08 checks require pinned external trust, genuine signed attestations and matching raw Devtool run-store receipts. Source-only statuses or missing evidence block release.
3. Verify NewFuture and bclone pinned provenance, independent reproducible builds, arm64 candidate files, physical root-manager matrix, exact-target ordinary Android-app read/write, reboot/endurance/fault cases, protected namespace safety, jobs/crypt/RC, standalone/embedded transports, screenshot/interaction/accessibility parity, and zero critical unresolved obligations. A root-shell observation is never evidence of an ordinary-app read/write result.
4. Verify an **externally issued** final attestation whose signing public key is out of the repo and pinned to an externally supplied SHA256 digest. Check signature over the raw JSON bytes, source commit/tree, eight gate results, required evidence categories, independent raw receipts and their hashes, and the final candidate file's exact SHA256. The verifier may recognize an already valid external seal but never signs or emits one itself.

## External inputs for independent qualification

`SKYBIND_FINAL_SEAL_EVIDENCE_DIR` points to a separately controlled external folder containing `final-attestation.json`, `final-attestation.sig`, `artifacts/<candidate-file>`, and `receipts/<gate-file>`; `SKYBIND_FINAL_SEAL_PUBKEY` points to an independent public verification key; `SKYBIND_FINAL_SEAL_PUBKEY_SHA256` is its externally established pin. The G03–G08 independent attestation trust sources use the separately defined `SKYBIND_VERIFIED_GATE_EVIDENCE_DIR`, `SKYBIND_GATE_TRUST_PUBKEY`, `SKYBIND_GATE_TRUST_KEY_SHA256` inputs.

Do **not** store signatures, private keys, trust pins, or user/device evidence inside Git or these overlays. An external reviewer must gather and validate real run receipts; no JSON status claim alone is sufficient. The candidate name must be a basename only, and its bytes must match the signed hash.

## Exit/status semantics

* `BLOCKED`, `final_seal: NOT_ISSUED`, exit **3** — mandatory evidence absent, source drift, missing/failed gates, tampering, or invalid signatures. This is the expected state after installing this Devtool overlay.
* `QUALIFIED`, `final_seal: VERIFIED_EXTERNALLY_ISSUED`, exit **0** — all independent evidence and external signature verified against the frozen source and candidate. This verifier does **not** write an attestation, change a gate, modify the source, or manufacture a seal.

**Automatic Devtool apply validation:** checks both positive *definition* behavior and adversarial denials, reads the live gate outcomes and requires the honest BLOCKED state, checks reproducibility of the read-only result and the lack of product-file writes, and records Devtool's native rollback/evidence. This test is not itself an independent release qualification. Before a production release, run the Devtool authoritative final-seal check for the selected target in addition to this verifier; keep their independent reports distinct. Device evidence must come from actual physical Android runs.
