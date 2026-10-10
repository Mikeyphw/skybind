# SB-R01 — Release provenance and mounted configuration lifecycle repair

**Assurance:** source-validated repair only. No upstream pin, real FUSE device evidence, G01–G08 qualification or final seal is issued.

## Release provenance

* Preserve the build-time-verified root `runtime.provenance.json` in the final installable candidate.
* Reject candidates missing, replacing or contradicting this manifest; check the documented runtime identity, required ARM64 members, sizes and digests against the assembled ZIP.
* Preserve deterministic candidate ZIP structure and original SPDX and SHA256SUMS coverage.
* A self-consistent local synthetic fixture is **not** independent provider provenance or an installable release qualification.

## Guarded registry publication

* Production `config.apply` and `config.rollback` route through the native lifecycle engine, not directly to the registry-only store.
* The registry's exclusive write lock is held while validating the proof and writing pending recovery state, then a callback quiesces **only** affected mounts by verifying their old ownership/process/mount identities before publishing.
* Failed ownership checks abort publication, never unmount or signal an unowned foreign process, and retain desired-state recovery.
* Mount deletions quiesce the old mount before the name disappears from the registry. Affected enabled mounts restart only if desired; an explicit prior stop remains stopped. Policy-only changes do not restart.
* The process/mount cleanup uses the recorded **old** mountpoint. A postpublication restart failure is reported as a published revision needing recovery and persisted in a private attention record, never misrepresented as a fully successful reconciliation.
* A pending transaction recovering on next daemon start restores the old registry when a process dies before publication. Desired state is not cleared by prepublication quiesce, allowing the supervisor to resume an old mount when appropriate.

## Automatic Devtool acceptance

`apply-overlay` executes `scripts/devtool/check_r01_runtime_mount.sh`: full Go and fixture suites, adversarial mounted-reconfiguration tests, both common umasks, supported-host race checks (unsupported is NOT_RUN, never PASS), `go vet`, Android ARM64 compile, and independent BLOCKED-gate checks. Preflight is source-hash guarded. No separate manual validation commands.

**Known limitations:** source tests exercise injected observers/spawners, not a physical Android filesystem; process death during a verified unmount can still require operator attention and supervisor recovery. Real upstream/source/device/UX evidence stays outstanding. SB-R02 is responsible for journal and WebUI integration defects.
