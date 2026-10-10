# SB-CG1 — Independent Devtool milestone gates

The **definitions** for SB-G03…SB-G08 are installed by one Devtool overlay. Their
**qualification** is evaluated separately, in dependency order, on frozen
product sources. Installing or testing these definitions is not promotion.

## Promise ledgers

Each `SB-G0x_PROMISE_LEDGER.json` carries the unchanged 45-item roadmap gate
requirements, original implementation dependencies, required negative/positive
checks, source scopes, evidence needs and assurance ceiling. The gates never
change app source, install anything on a device, or issue a final seal.

## Gate dependencies and ceilings

| Gate | Dependencies | Highest qualification this gate can issue |
| --- | --- | --- |
| G03 | G02 | Host lifecycle, supervisor/cache/policy safety |
| G04 | G03 | Android namespace **source** safety, not device release |
| G05 | G03 | Jobs/RC/remotes/crypt backend source safety |
| G06 | G02,G04,G05 | Diagnostics and Web transport source security |
| G07 | G06 | Browser screenshots/flows, WebView and accessibility parity |
| G08 | G01..G07 | Device and candidate release readiness (not final seal) |

All G01–G08 must be independently evidenced before SB-CFS1 can make an
independent final seal decision. Gates share **no implicit blanket pass**.

## Independent evidence policy

Evidence comes from an **external verified evidence directory**, never the
repository, and is authenticated using an external public key whose SHA-256
must be independently pinned. The evaluator creates no trust keys, signatures,
run-store receipts or device evidence.

External trusted reviewer provides `SKYBIND_VERIFIED_GATE_EVIDENCE_DIR`,
`SKYBIND_GATE_TRUST_PUBKEY` and `SKYBIND_GATE_TRUST_KEY_SHA256` through its
secure Devtool workflow. These are intentionally NOT populated in Skybind.

For each gate, `<evidence_root>/<gate>/` must have:

- `attestation.json`, `attestation.sig` (signature verified using OpenSSL on the
  exact JSON bytes, trusted public key SHA-256 pinned independently)
- `runs/<32-character-devtool-run-id>/run.json` for at least two distinct,
  separately verified fresh Devtool run-store receipts, whose SHA-256 hashes
  are pinned in the signed `run_receipts` array
- `attachments/<basename>` for each signed raw evidence hash

The signed attestation must identify gate, product, exact source commit and
source-scope SHA-256, complete positive/negative checks, zero unresolved
obligations/warnings, independent Devtool run identities and categorical
attached evidence. **A signed claim alone is insufficient**; the raw receipts
and attachments must match. The independent reviewer is responsible for
cryptographically authenticating Devtool's original run-store identity before
signing its attestation; this evaluator independently checks the frozen hashes
and source-bound receipt contents. This is not a claim that an arbitrary user
can manufacture an independent Devtool run.

For G07 the evidence categories must include reference screenshots, browser
interactions, embedded Android WebView captures and accessibility. For G08 they
must include **both verified real upstream providers**, physical rooted-device
manager matrix, ordinary unprivileged app FUSE file read/write, reboot
endurance and reproducible release. Unit tests, test fixtures, emulators,
root-shell reads or a build ZIP do not satisfy these requirements.

## Validation and exit codes

The source overlay runs read-only six-gate tests and two independent subprocess
assessments via Devtool. `BLOCKED`/exit 3 is an expected *evaluation outcome*
when evidence is absent; the Devtool overlay validator succeeds only when that
blocked outcome is truthful and consistent. Actual permission to promote a gate
requires `PASS` from the independent source-frozen gate evaluator.

SB-CFS1 final seal remains **NOT_ISSUED** and is a separate future artifact.
