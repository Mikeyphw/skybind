# SB-Q14R2 private-repository replacement

The GitHub Attestations API is unavailable for private personal repositories without Enterprise Cloud. **This document is superseded by `SB-Q14_PRIVATE_REPOSITORY_PROVENANCE.md`.** Q14R2 uses Ed25519 owner-managed signatures stored in private Actions artifacts, with an owner-pinned out-of-band public trust anchor. It cannot independently qualify G01–G08 or issue a release seal.

---

# SB-Q14 — GitHub candidate provenance, not final release qualification

## Q14R1 signing repair

The Q14 run `38333520326` reached `actions/attest` on both lanes and failed with
`predicate-type must be provided`. Q14R1 fixes the workflow by pinning
`actions/attest` v4.0.0 to its complete immutable commit and requiring
`artifact-metadata: write`, while keeping `subject-path` for automatic SLSA
provenance. Do not supply fabricated custom predicates and do not reuse old
unsigned results as signed evidence.

Commit/push Q14R1 and start a **new** `workflow_dispatch` run. Keep
CFS1 G01–G08 independently blocked until its actual evidence is verified.

SB-Q13 run `38328621356` produced raw, byte-identical provider candidate reports. The
user-uploaded archive contains only the comparison report, not the original candidates.
SB-Q14 **fetches original A/B candidate artifacts** through authenticated `gh` API,
validates their source receipts and content with SB-Q12/Q13, and optionally verifies
GitHub's OIDC/Sigstore SLSA build attestations. The Q13 workflow had no attestations:
its output MUST remain `NO_Q13_ATTESTATIONS_EXPECTED` even if original bytes match.

Run after applying Q14:

```sh
cd ~/Code/skybind
./devtoolw q14                    # examine historical Q13 run 38328621356
```

Q14 adds `.github/workflows/skybind-q14-attested-candidates.yml`. Commit and push it,
then invoke a **new run** after checking GitHub Actions permissions allow artifact
attestations for the repository (a public repository generally qualifies):

```sh
gh workflow run skybind-q14-attested-candidates.yml
# find the new numeric run ID:
gh run list --workflow skybind-q14-attested-candidates.yml --limit 3
# After success, authenticate the run and verify original artifacts:
python3 scripts/dev/release/q14_attestation.py --run-id NEW_RUN_ID --repo Mikeyphw/skybind
```

The checker leaves raw A/B ZIPs in `Download/skybind-q14-run-NUMBER/`, writes
`skybind-q14-summary.json` and `skybind-q14-summary.md`, and requires:

- GitHub Actions API: exact owner/repo, workflow path, completed successful run, commit SHA.
- Source receipts: exact run commit, clean build inputs, both provider binaries in both lanes.
- Byte-for-byte A/B ZIP identity and cross-provider daemon/FUSE parity.
- `gh attestation verify --repo ... --signer-workflow ... --source-digest ...`
  with GitHub certificate/Sigstore and SLSA subject digest checks, denying self-hosted runners.
- Original CFS1 evaluator to enumerate remaining G01–G08 gate blockers.

`gh attestation verify` requires GitHub CLI with attestation support and online API
access; missing signatures or tools are **never treated as passing**. Signed provenance
proves signed GitHub workflow claims for the original ZIP digests; it is not a certified
independent builder and does NOT qualify the physical device, kernel/root manager matrix,
negative security tests, WebView matrix, G01–G08 gates, or final seal.

To ensure a clean rerun, **move or archive** the existing `skybind-q14-run-NUMBER/`
folder before repeating the command. The checker refuses to reuse prior evidence.

GitHub hosted runner generation includes `id-token: write` and `attestations: write`.
The workflow pins `actions/attest` v4.0.0 to its verified full commit `c32b4b8b198b65d0bd9d63490e847ff7b53989d4`. Version 4 generates the SLSA provenance predicate automatically from `subject-path`; v3 generic attestation did not and caused `predicate-type must be provided` in run `38333520326`. The failed historical run cannot be retroactively signed. Signing failures
must fail the workflow; no silent unsigned fallback. The working Android module is
neither rebuilt nor modified.
