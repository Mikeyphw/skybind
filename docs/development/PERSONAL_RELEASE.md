# Skybind — Personal Release (not CFS1)

Skybind has two independent tracks:

- **Personal:** verified local build, intended for the owner's KernelSU device. No third-party signer, physical test matrix or CFS1 G01–G08 prerequisites. Actual FUSE security and packaging integrity remain enforced.
- **Formal CFS1:** the existing optional independent release process, with its full original G01–G08 requirements. This change does not mutate its code, allowlist, verification rules, or release seal.

Every Personal ZIP is still internally marked `CANDIDATE_ONLY_NOT_SEALED` to retain the original integrity verifier's expectations. The external filename `Skybind-bclone-PERSONAL.zip` is a **distribution label, not a forged seal**. A personal build is not an attested release.

## Day-to-day Termux commands

```sh
cd ~/Code/skybind
./devtoolw test                 # Go tests + vet + WebUI checks, no package
./devtoolw build-bclone         # existing verified local candidate; no distribution
./devtoolw personal-release     # tests, builds bclone, verifies, stages KernelSU ZIP to Downloads
# or
./devtoolw personal-release-newfuture
```

Result: `/storage/emulated/0/Download/Skybind-Personal-<provider>-<timestamp>-<hash>/Skybind-<provider>-PERSONAL.zip`, with `SHA256SUMS`, `PERSONAL_BUILD.json`, and instructions. Build never installs or restarts the existing module. A missing/wrong pinned toolchain or provider evidence blocks packaging and is reported, not silently replaced.

Optional formal release scripts and `./devtoolw q11` … `q17` remain available; they do not block the Personal track. Never present `PERSONAL_BUILD.json` as independent evidence or CFS1 gate acceptance.
