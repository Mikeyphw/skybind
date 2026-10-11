# SB-Q01 — Real evidence qualification kickoff (no gate promotion)

**Definition validation != milestone PASS.** The CLI invokes real independent
`SB-G01` … `SB-G08` plus `SB-CFS1`; a successful CLI invocation can still report
all eight **BLOCKED**. This is a diagnostic, not a source pin or seal.

## On your local Termux Zsh checkout

```zsh
cd ~/Code/skybind
python3 scripts/dev/qualification/skybind_qualify.py status
```

Capture a raw (not attested) read-only state report OUTSIDE Git if needed:

```zsh
python3 scripts/dev/qualification/skybind_qualify.py status --output ~/Downloads/skybind-gate-raw.json
```

## G01: prerequisite to every other gate

1. Obtain the exact original NewFuture `v1.75.0` `magisk-rclone_arm64-v8a.zip`
   from the upstream publisher, verifying publisher/release provenance
   *independently* (not merely a URL named like the project).
2. Run `python3 scripts/dev/qualification/skybind_qualify.py inspect-newfuture ~/Downloads/magisk-rclone_arm64-v8a.zip`
   to verify shape and compute a **candidate** SHA256. The digest alone does not
   authenticate GitHub provenance and this script will never insert the pin.
3. Independently verify and review that hash; pin it manually in
   `scripts/dev/runtime/source.lock.json` in a reviewed Devtool source change.
4. Choose and independently verify one immutable bclone commit and matching
   Android NDK/Go compiler versions. Use `inspect-bclone PATH` to report the
   checkout state, but never accept a self-asserted source identity.
5. Build both providers independently **twice**, compare byte hashes, archive
   underlying real helper provenance and compile logs. Synthetic fixture
   success does not qualify. The trusted reviewer must independently attest
   official sources, reproducibility and native Devtool receipt provenance.

G02 requires G01, a frozen source commit and two verified clean Devtool run-store
receipts plus the full negative-case matrix. Its current JSON schema is described
by `scripts/dev/gates/sb_g02.py`. Then G03 → G04/G05 → G06 → G07 → G08 and
finally externally issued SB-CFS1, only after physical ordinary-app reads,
root-manager matrix, WebUI reference screenshots and reboot endurance.

This preflight deliberately does **not** generate fake gate attestations,
private keys, trust pins or human/device evidence. No optional local report is
sufficient to mark a gate as PASS.
