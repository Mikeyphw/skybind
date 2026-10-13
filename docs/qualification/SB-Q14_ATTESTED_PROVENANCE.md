# SB-Q14 — GitHub candidate provenance, not final release qualification

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
The workflow pins the attestation action by its full commit hash. Signing failures
must fail the workflow; no silent unsigned fallback. The working Android module is
neither rebuilt nor modified.
