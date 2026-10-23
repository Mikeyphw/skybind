# Skybind — personal release process (SKYBIND_PERSONAL_V1)

This replaces the old independent external release-seal track for the personal
project. **It is not an external security certification.** All third-party
attestation, G01/G02 custody signature, fixed-point independent authority,
Magisk/KernelSU/KernelSU Next/APatch four-manager matrix and final signed seal
requirements are removed from the active release path.

## Build and test

Use the existing `./devtoolw test` and `./devtoolw personal-release` (or
`./devtoolw personal-release-newfuture`) to run verified Go/WebUI tests and
produce a deterministic Personal ZIP. The builder checks source/toolchain pins,
provider identity, ELF format, package inventory and SHA-256. It does not
pretend installing a module or UI acceptance happened.

## Attach existing local evidence, once

```sh
cd ~/Code/skybind
python3 scripts/dev/qualification/personal_policy.py configure \
  --q16 /storage/emulated/0/Download/skybind-q16-summary.json \
  --q17 /storage/emulated/0/Download/skybind-q17-summary.json \
  --r1 /path/to/consolidated-r1-receipt.json \
  --m2-m3 /path/to/m2m3-nine-lane-receipt.json
python3 scripts/dev/qualification/personal_policy.py check
```

The private owner evidence index is created once at
`~/.local/state/skybind/personal-release/evidence.json`, bound by SHA-256.
None of the first-party receipts are treated as independent signatures. The
older receipts remain acceptable when their nine product-file hashes and
source lock match the exact evidence baseline; gate-tooling-only changes do
not force rebuilding APKs.

## Approve *your* selected device and ZIP

After personally checking the actual interface and device behavior:

```sh
python3 scripts/dev/qualification/personal_policy.py approve \
  --candidate /storage/emulated/0/Download/Skybind-Personal-bclone-XXXX/Skybind-bclone-PERSONAL.zip \
  --manager kernelsu --ui-reviewed --device-reviewed \
  --accept-personal-scope
python3 scripts/dev/seal/sb_cfs1.py
```

The approval file is source-, evidence- and candidate-hash bound. No private
key, external reviewer or root-manager matrix is required. **Do not tick
`--ui-reviewed` or `--device-reviewed` unless you actually checked them.**
The result `PERSONAL_RELEASE_APPROVED` describes owner approval of this exact
ZIP for one device, not universal Android compatibility or external assurance.

Only a clean committed checkout can be approved. Approval never executes a
job, grants root, installs a module or changes device data. Installation is a
separate explicit action via existing Devtool workflows.
