# SB-Q04P3 — Pinned NDK installer SIGPIPE repair (not release qualification)

## Observed failure

GitHub Actions run `38106935811`, commit `f10588782a27c46d830639db753c771c5e95ef1c`:
Both `pinned-provider-lanes` jobs failed in **Install pinned NDK (no mutable runtime)** with
`yes: standard output: Broken pipe` while the step ran `set -euo pipefail` and
`yes | sdkmanager 'ndk;28.2.13676358'`.

When `sdkmanager` closes its stdin, `yes` can exit nonzero due to SIGPIPE even if
`sdkmanager` installed the NDK successfully.  `pipefail` converted that into a
false installation failure.  The logs **do not prove** whether sdkmanager
successfully installed the package because the old script stopped before checking it.

## Scope of the repair

- Preserve `set -euo pipefail` for the full step, turning off **pipefail only for
  the license-answering pipeline**. The last command in the pipeline remains
  `sdkmanager`, so its own exit code determines pipeline success. `set -e`
  continues to stop CI if `sdkmanager` fails.
- Suppress expected stderr from `yes`, not error output from `sdkmanager`.
- Verify `source.properties` declares exactly `Pkg.Revision = 28.2.13676358`,
  and the installed NDK contains executable Android/arm64 API 21 clang.
- Keep the exact NDK, Go, NewFuture prebuilt and bclone lock inputs unchanged.
- Exercise the actual workflow Bash block with mock Android SDKs, including a
  nonzero upstream `yes`, a failed installer, missing files and wrong NDK
  revisions. No network tools or external binaries are needed by these tests.

## Qualification statement

This repair is a source-level CI correctness change. Local mock tests are not
real NDK acquisition, source reproducibility, Android device evidence,
independent supply-chain attestation, G01 approval or any final signing.

**G01–G08 BLOCKED · Final seal NOT_ISSUED.**
