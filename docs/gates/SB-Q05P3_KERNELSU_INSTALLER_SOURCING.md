# SB-Q05P3 — KernelSU source-installed module hook repair

## Observed physical install failure

The user-supplied KernelSU installation log from 2026-10-11 shows extraction of
81.98 MB bclone candidate and `- Skybind: fixed runtime/module layout verified`,
then `sh: REPLACE: parameter not set` followed by module installation failure.
**This installation did not complete.** Do not mark a device gate PASS.

## Root cause and scope

KernelSU **sources** `customize.sh` into its installer shell. The old hook used
`set -eu`, enabling nounset in the parent. The installer then references the
optional `REPLACE` variable, which is not always initialized. The shell aborts.
Official KernelSU module installation code processes `REPLACE` and `REMOVE`
*after* sourcing the hook.

## Repair

- Do not modify shell options from sourced installer hooks.
- Define `REPLACE=''` and `REMOVE=''` explicitly, as Skybind does not replace or
  remove system directories. This preserves an additive, root-manager-owned mount.
- Retain fail-closed checks for module identity, required executables, hook
  existence and chmod, using installer `abort` for controlled cleanup.
- Exercise source/continuation in POSIX `sh` including an unset `REPLACE`, parent
  `nounset`, missing inputs, symlinks, and permission failures.
- Add the regression to the manually dispatched Q05 candidate assembly workflow.
- No shell download, dynamic runtime selection, boot changes, or prior release
  evidence mutation. The Q05 candidate ZIPs from CI run 38114952297 contain the
  **old** hook and must not be retried unchanged.

## Qualification

Test fixtures do not represent a physical root manager. After merging and
re-running Q05 candidate CI, re-audit the new candidate then attempt a controlled
KernelSU install with recovery arrangements. G01–G08 remain BLOCKED and
FINAL SEAL remains NOT_ISSUED.
