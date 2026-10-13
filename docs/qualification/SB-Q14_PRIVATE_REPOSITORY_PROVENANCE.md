# SB-Q14R2 — Private-repository candidate signing (no GitHub Attestations API)

## Why

GitHub's repository-hosted artifact attestation storage is not enabled for personal private repositories on ordinary Free/Pro/Team plans. The previous Q14R1 step failed after building both candidates. **Do not make Skybind public for this.**

Q14R2 uses OpenSSL Ed25519 to sign a canonical JSON manifest **including the original SHA-256 for each candidate ZIP and build-time receipt**, repository, commit, workflow, run ID, attempt, and lane. The raw candidate ZIPs, manifest, detached signature, and public key are stored together in private GitHub Actions artifacts. No signing API or public Rekor transparency log is used. It runs on Ubuntu's preinstalled OpenSSL.

### One-time private setup (run in Termux)

```bash
cd ~/Code/skybind
bash scripts/dev/release/q14_private_key_setup.sh Mikeyphw/skybind
```

Requires authenticated `gh`, `openssl`, `base64`, and `sha256sum`. This creates a private Ed25519 PEM in `~/.config/skybind/trust/q14-ci-private.pem` (permissions 0600), a public trust anchor in `~/.config/skybind/trust/q14-ci-public.pem`, uploads the private key base64 as a GitHub Actions secret named `SKYBIND_Q14_ED25519_KEY_B64`, and uploads its public-key SHA-256 as the repository variable `SKYBIND_Q14_SIGNER_PUBLIC_SHA256`. It refuses to silently rotate an existing key. Never commit the private key or upload it here.

Back up the private PEM securely. A repository administrator can rotate secrets; keeping the public trust anchor *outside* downloaded artifacts is what makes the local verification meaningful. Keep that PEM too.

### Build signed private artifacts

```bash
cd ~/Code/skybind
git push
gh workflow run skybind-q14-attested-candidates.yml --ref main
gh run list --workflow skybind-q14-attested-candidates.yml --limit 3
```

After successful run, verify the actual CI artifacts using Q14R2's source-bound command:

```bash
python3 scripts/dev/release/q14_attestation.py \
  --repo Mikeyphw/skybind --run-id RUN_ID \
  --trusted-public-key "$HOME/.config/skybind/trust/q14-ci-public.pem"
```

Each lane's manifest is verified using the **externally pinned public key**, then its repository, workflow, SHA, run ID, attempt, lane, and all three file digests are matched against actual downloaded bytes. The existing Q12/Q13 validators separately verify candidate ZIP format, build receipts, A/B reproducibility, and shared provider components. Old failed runs cannot be retroactively signed.

### Assurance and security limits

- **PRIVATE_CI_SIGNATURE_VERIFIED_NOT_CFS1**: Signature and candidate hashes cryptographically verified to the locally pinned Ed25519 public key. This is *maintainer-controlled signing*, **not independent source/build custody**. Both A and B lanes use the same signing authority.
- **No public transparency log**: keeps repository name and build hashes out of the public Sigstore Rekor log, but also foregoes Rekor's timestamped transparency benefit.
- **No trust on first use from the artifact**: Q14R2 does not accept the downloaded `candidate-signer-public.pem` as an independent trust anchor. Configure the local key first.
- No CFS1 gate is promoted. SB-G01–G08 and final seal still require independent receipts and external authority. Q14R2 remains `NOT_ISSUED`.
- The workflow uses user-controlled Actions secrets and variables, and builds only on a manually dispatched workflow. Protect write access to the repository, workflow, and GitHub secrets.
- For stronger custody later, move the signing key into a KMS or an independent signer; don't treat a maintainer secret as an external endorsement.

### Expected failure states

- No GitHub secret/variable: the signing job fails with a clear configuration message (not the GitHub private repository attestation error).
- Candidate tampered: hash check or signature verification fails.
- Mismatched repo, run, SHA, lane, or attempt: signed manifest rejected.
- Missing/wrong trusted public key: signature status unverified/rejected, never automatically promoted.
- Failed or unsigned older Q14 workflow runs: no retrofit signatures.
