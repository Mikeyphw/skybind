# SKYBIND — Consolidated Devtool Implementation Roadmap

**Status: SB-C01 implemented at SOURCE_ONLY assurance; G01/G02 BLOCKED, no Android mount qualification or release seal.**

## Decision: 34 remaining obligations, only 8 future overlay artifacts

The previous campaign separated 36 implementation obligations, 8 milestone gates and one seal into 45 potential archives. Nine implementation obligations (`SB-O01`–`SB-O09`) and two **gate definitions** (`SB-G01`, `SB-G02`) have been delivered; those gate **qualifications remain BLOCKED**, not passed. The remaining 27 feature obligations, six gates, and final seal are **retained in full** and delivered through **six substantial implementation overlays + one independent gate package + one final seal = eight overlay ZIPs**.

| Measure | Previous approach | Consolidated approach |
|---|---:|---:|
| Remaining feature obligations | 27 | 27 (unchanged) |
| Remaining gate obligations | 6 | 6 (unchanged) |
| Final seal obligations | 1 | 1 (unchanged) |
| **Future Devtool overlay ZIPs** | **34** | **8** |

**Counting rule:** the old `SB-Oxx` labels remain *obligation IDs* and are never treated as additional future archives. Gate IDs (`SB-G01`–`SB-G08`) likewise remain independent acceptance decisions even when gate definitions are shipped in one package. Existing implemented overlays are never reapplied or renamed retroactively. The `SB-Cxx` labels below are actual planned new artifact IDs.

**Active contract:** `SB-C01` atomically updated the repository checker, tests, `.devtool.toml`, and `docs/roadmap` to use the eight-artifact delivery index while retaining the original 45-obligation ledger and all 57 typed API operations. Source validation is automatic through Devtool; source completion does not imply milestone/device qualification.

**No features are removed.** The complete baseline specification remains `SKYBIND_FEATURE_SPEC.md`; source-by-source implementation, tests, negatives and promotion criteria from every old obligation are copied verbatim into the machine-readable index and the detailed appendix below. The 57 typed operations are re-mapped there without removal.

## Planned delivery sequence

| Order | New artifact | Retained obligations | Subsystem | Gate evidence |
|---|---|---|---|---|
| 1 | `SB-C01` | SB-O10, SB-O11, SB-O12, SB-O13, SB-O14 | Owned FUSE Mount Engine, Supervisor, Resource Policies & Cache | SB-G03 |
| 2 | `SB-C02` | SB-O15, SB-O16, SB-O17, SB-O18, SB-O19 | Android Namespace Visibility & Root-Manager Lifecycle | SB-G04 |
| 3 | `SB-C03` | SB-O20, SB-O21, SB-O22, SB-O23, SB-O24 | Jobs, Authenticated RC, Remote Browsing & Crypt | SB-G05 |
| 4 | `SB-C04` | SB-O25, SB-O26, SB-O27, SB-O28 | Doctor, Support Bundles & Both Secure WebUI Transports | SB-G06 |
| 5 | `SB-C05` | SB-O29, SB-O30, SB-O31, SB-O32, SB-O33 | Original WebUI Direct Port & Full Visual/Interaction Parity | SB-G07 |
| 6 | `SB-C06` | SB-O34, SB-O35, SB-O36 | Whole-Product Integration, Device Matrix & Reproducible Release | SB-G08 |
| 7 | `SB-CG1` | SB-G03, SB-G04, SB-G05, SB-G06, SB-G07, SB-G08 | Independent Milestone Gate Definitions & Execution (G03–G08) | G03–G08 independently |
| 8 | `SB-CFS1` | SB-FS1 | Final Skybind Whole-Product Qualification Seal | SB-FS1 |

**Dependencies:** C01 → C02 and C03 (C02/C03 may be developed independently after C01) → C04 → C05 → C06 → CG1 → CFS1. The original source requirements that refer to blocked gates remain **hard qualification/promotion gates**, not permission to fake device evidence. Source development and targeted test implementation may progress under `SOURCE_ONLY / NOT_ATTESTED`; production promotion cannot.

## Shared Devtool execution contract — applies to every new overlay

1. **No manual validation for operators.** A single `devtool -r . --target skybind apply-overlay ~/Downloads/<artifact>.zip --keep-artifact` invokes supported Devtool preflight, inventory verification, targeted validation, negative/security tests, post-validation checks, commit/rollback and evidence collection automatically. Cross-target validation goes in the declared Devtool workflow graph, not a list of manual shell commands.
2. **Actual Devtool machinery:** exact schema-v2 inventory including source/payload SHA-256, JSON-v1 read-only hooks, repository identity/target guards, dependency DAG/affected-input selection, built-in transaction/rollback, isolated validation, warning-budget checks, durable phase/checkpoint/evidence sessions for long tests, artifact provenance, run-store and history. Use source-based platform discovery instead of invented commands or false passes.
3. **Bounded and independently attributable tests inside larger overlays.** Every old `SB-Oxx` item is a separate named workstream with its own test results, negative cases, file ownership and acceptance. A failure in any workstream fails the **whole implementation artifact** and Devtool rolls it back. Distinct packages do not have to exist for distinct test receipts.
4. **Host portability first:** writable private TempDir and `TMPDIR` (never `/tmp`), short Unix-socket fixtures on Android, explicitly chmod unsafe permission-test fixtures under `umask 077`, and host-capability-aware race checks. The absence of Android/arm64 race support is recorded `NOT_RUN_UNSUPPORTED`, never as a success; run any required race evidence on a capable host at the corresponding gate.
5. **No artifact-generated worktree dirt:** cross-compile binaries to isolated output, clean temporary fixtures, use process locks, avoid uncontrolled CLI invocations. Exact pinned hashes, rollback and safe ownership invariants remain compulsory.
6. **Gate truth:** a Devtool application may prove that a gate checker correctly produces `BLOCKED`, but that does **not** mean the gate has passed. Final gate promotion requires fresh-process independent evidence against frozen commits. G01/G02 are already definition-installed and remain blocked until their original evidence is satisfied.
7. **Original WebUI:** copy the eight original assets directly as source; preserve visual and interaction behavior practically exactly. Only branding, narrow API wiring, explicitly excluded controls and independently justified security/accessibility fixes may differ; record any visual delta. No redesigned frontend or substituted framework.
8. **Explicit exclusions:** do not implement dynamic/replaceable installed runtime, install-time provider switching/download/update or any migration/history-conversion flows. Build-time provider input, static runtime integrity, config rollback, Devtool validation recovery and normal release management are retained.

## Overlay contracts, validation and non-negotiable negative cases

### SB-C01 — Owned FUSE Mount Engine, Supervisor, Resource Policies & Cache
**Archive:** `skybind-SB-C01-mount-engine.devtool-overlay.zip`

**Dependencies:** `SB-O09`. **Promotion gates:** `SB-G02`. **Targets:** `skybind`, `skybind_runtime_inputs`. **Risk:** high. **State:** `SOURCE_IMPLEMENTED_NOT_PROMOTED`.

**Retained original obligations:** `SB-O10`, `SB-O11`, `SB-O12`, `SB-O13`, `SB-O14`.

**Complete feature workstreams:**
- Ownership-checked FUSE launch/stop/restart and desired/observed state.
- Readiness graph, health classification, recovery and persistent retry budgets.
- Network/charging/battery/VFS policies, cache accounting, safe eviction and guarded cache actions.

**Minimum negative acceptance cases:**
- PID reuse or foreign mount must never be terminated/unmounted.
- Explicit STOPPED survives reboot; remote outages do not create restart storms.
- Unknown metering never counts as unmetered.
- Cache traversal, active-file deletion and symlink attacks must fail closed.

**Gate relationship:** `SB-G03` is a separately evaluated milestone with its own evidence ledger. This artifact installs and source-validates features; it cannot assert that gate is passed.
**Files and packages covered:** `.devtool.toml`, `docs/roadmap`, `internal/cache`, `internal/daemon`, `internal/mounts`, `internal/mounts/config`, `internal/mounts/health`, `internal/mounts/lifecycle`, `internal/policy`, `internal/previewproof`, `internal/readiness`, `internal/runtimeauth`, `internal/supervisor`, `internal/vfs`, `scripts/devtool/bootstrap_contract.py`, `tests/cache`, `tests/contracts`, `tests/devtool`, `tests/mounts`, `tests/policy`, `tests/readiness`, `tests/recovery`. A real implementation may add narrowly justified source/test paths with inventory updates, but cannot silently omit any retained obligation.
**Devtool validation:** run the targeted positive and negative tests for **every** subordinate old obligation (see appendix and JSON), impacted dependent suites, cross-target integration fixtures, security scans, source attribution and freshness; rollback on any failure. Real-device-only checks become explicit `device_unverified`, never a false pass.

### SB-C02 — Android Namespace Visibility & Root-Manager Lifecycle
**Archive:** `skybind-SB-C02-android-platform.devtool-overlay.zip`

**Dependencies:** `SB-C01`. **Promotion gates:** `SB-G03`. **Targets:** `skybind`, `skybind_android_device`. **Risk:** critical. **State:** `PLANNED`.

**Retained original obligations:** `SB-O15`, `SB-O16`, `SB-O17`, `SB-O18`, `SB-O19`.

**Complete feature workstreams:**
- Read-only Android multi-user mount-namespace topology, exact target versus alias classification.
- Opt-in namespace bind planner with topology proofs, protected-process denies and rollback.
- Owned bind journal, recovery, controlled reconciliation.
- Magisk/KernelSU/KernelSU Next/APatch module hooks, install, boot, Action, uninstall/purge.

**Minimum negative acceptance cases:**
- Never mutate protected shared namespaces or treat an alias as exact target.
- Namespace churn/identity mismatch denies mutation.
- Rollback only proven owned binds and never unmount unrelated processes.
- Uninstall preserves persistent state unless explicit separately proven purge.

**Gate relationship:** `SB-G04` is a separately evaluated milestone with its own evidence ledger. This artifact installs and source-validates features; it cannot assert that gate is passed.
**Files and packages covered:** `internal/namespace`, `internal/namespace/inspect`, `internal/namespace/mutation`, `internal/namespace/ownership`, `internal/namespace/reconcile`, `internal/namespace/topology`, `internal/paths`, `internal/platformlifecycle`, `internal/platformstate`, `internal/previewproof`, `internal/rootmgr`, `module/action.sh`, `module/customize.sh`, `module/module.prop`, `module/post-fs-data.sh`, `module/service.sh`, `module/uninstall.sh`, `tests/namespace`, `tests/platform`. A real implementation may add narrowly justified source/test paths with inventory updates, but cannot silently omit any retained obligation.
**Devtool validation:** run the targeted positive and negative tests for **every** subordinate old obligation (see appendix and JSON), impacted dependent suites, cross-target integration fixtures, security scans, source attribution and freshness; rollback on any failure. Real-device-only checks become explicit `device_unverified`, never a false pass.

### SB-C03 — Jobs, Authenticated RC, Remote Browsing & Crypt
**Archive:** `skybind-SB-C03-jobs-providers.devtool-overlay.zip`

**Dependencies:** `SB-C01`. **Promotion gates:** `SB-G03`. **Targets:** `skybind`. **Risk:** high. **State:** `PLANNED`.

**Retained original obligations:** `SB-O20`, `SB-O21`, `SB-O22`, `SB-O23`, `SB-O24`.

**Complete feature workstreams:**
- Revisioned jobs, persisted due-run claim and at-most-once execution.
- Copy/sync/check executor, progress/cancel/policies, destructive sync proof.
- Per-mount authenticated loopback-only RC metrics isolation.
- Root-private rclone remote discovery and bounded browsing.
- User-defined password, obscured storage, crypt wrapper creation and safe rollback.

**Minimum negative acceptance cases:**
- No duplicate due run on daemon restart and no unconfirmed sync delete.
- No generic RC proxy, leaked credentials or externally reachable RC.
- No arbitrary remote traversal or secret export.
- Reject self-crypt, nested crypt, malformed credentials and half-published config.

**Gate relationship:** `SB-G05` is a separately evaluated milestone with its own evidence ledger. This artifact installs and source-validates features; it cannot assert that gate is passed.
**Files and packages covered:** `internal/jobs/executor`, `internal/jobs/registry`, `internal/jobs/scheduler`, `internal/journal`, `internal/mounts/lifecycle`, `internal/previewproof`, `internal/provider/browse`, `internal/provider/crypt`, `internal/provider/password`, `internal/provider/remote`, `internal/rc`, `internal/runtimeauth`, `tests/crypt`, `tests/jobs`, `tests/provider`, `tests/rc`. A real implementation may add narrowly justified source/test paths with inventory updates, but cannot silently omit any retained obligation.
**Devtool validation:** run the targeted positive and negative tests for **every** subordinate old obligation (see appendix and JSON), impacted dependent suites, cross-target integration fixtures, security scans, source attribution and freshness; rollback on any failure. Real-device-only checks become explicit `device_unverified`, never a false pass.

### SB-C04 — Doctor, Support Bundles & Both Secure WebUI Transports
**Archive:** `skybind-SB-C04-diagnostics-transports.devtool-overlay.zip`

**Dependencies:** `SB-C02`, `SB-C03`. **Promotion gates:** `SB-G04`, `SB-G05`. **Targets:** `skybind`, `skybind_webui`. **Risk:** high. **State:** `PLANNED`.

**Retained original obligations:** `SB-O25`, `SB-O26`, `SB-O27`, `SB-O28`.

**Complete feature workstreams:**
- Structured sanitized log/Doctor with truthful PASS/WARN/FAIL.
- Private redacted bounded support ZIP with secret-canary checks.
- Authenticated localhost WebUI bootstrap/session/cookie/CSRF/Origin/Host defenses.
- Embedded root-manager fixed bridge with identical typed operation semantics.

**Minimum negative acceptance cases:**
- No credentials in logs/support artifacts.
- No generic command/RC passthrough.
- Reject token replay, XSS/CSRF, Host/Origin confusion and wrong transports.
- Standalone vs embedded operation result/error parity required.

**Gate relationship:** `SB-G06` is a separately evaluated milestone with its own evidence ledger. This artifact installs and source-validates features; it cannot assert that gate is passed.
**Files and packages covered:** `cmd/skybind`, `internal/control`, `internal/diagnostics`, `internal/doctor`, `internal/doctor/support`, `internal/integrity`, `internal/webui/bridge`, `internal/webui/http`, `module/action.sh`, `module/webroot/bridge.js`, `tests/doctor`, `tests/support`, `tests/webui-bridge`, `tests/webui-transport`. A real implementation may add narrowly justified source/test paths with inventory updates, but cannot silently omit any retained obligation.
**Devtool validation:** run the targeted positive and negative tests for **every** subordinate old obligation (see appendix and JSON), impacted dependent suites, cross-target integration fixtures, security scans, source attribution and freshness; rollback on any failure. Real-device-only checks become explicit `device_unverified`, never a false pass.

### SB-C05 — Original WebUI Direct Port & Full Visual/Interaction Parity
**Archive:** `skybind-SB-C05-original-webui.devtool-overlay.zip`

**Dependencies:** `SB-C04`. **Promotion gates:** `SB-G06`. **Targets:** `skybind_webui`, `skybind`. **Risk:** high. **State:** `PLANNED`.

**Retained original obligations:** `SB-O29`, `SB-O30`, `SB-O31`, `SB-O32`, `SB-O33`.

**Complete feature workstreams:**
- Direct copy of eight immutable-reference HTML/CSS/JS/image/config assets.
- Home/Mounts card-actions and four-stage creation wizard.
- Jobs, Activity, Runtime, Remotes, Doctor, Logs, Settings.
- Phone safe areas, responsive breakpoints, dark/light, dense, keyboard/touch/back, accessibility.
- Dual transport end-to-end UI and actual original-source screenshot/interaction diff.

**Minimum negative acceptance cases:**
- No unapproved redesign, reflow, feature removal or renamed action.
- An excluded control may be removed only with narrowly audited reason.
- No lying offline/progress/restart indicators.
- Broken mobile focus, gestures, dialogs, proofs or transport parity blocks.

**Gate relationship:** `SB-G07` is a separately evaluated milestone with its own evidence ledger. This artifact installs and source-validates features; it cannot assert that gate is passed.
**Files and packages covered:** `docs/ux`, `module/webroot/app.js`, `module/webroot/bridge.js`, `module/webroot/icon.png`, `module/webroot/index.html`, `module/webroot/model.js`, `module/webroot/style.css`, `tests/webui/a11y`, `tests/webui/fixtures`, `tests/webui/home-mounts`, `tests/webui/interaction`, `tests/webui/jobs-activity`, `tests/webui/secondary`, `tests/webui/visual`. A real implementation may add narrowly justified source/test paths with inventory updates, but cannot silently omit any retained obligation.
**Devtool validation:** run the targeted positive and negative tests for **every** subordinate old obligation (see appendix and JSON), impacted dependent suites, cross-target integration fixtures, security scans, source attribution and freshness; rollback on any failure. Real-device-only checks become explicit `device_unverified`, never a false pass.

### SB-C06 — Whole-Product Integration, Device Matrix & Reproducible Release
**Archive:** `skybind-SB-C06-integration-release.devtool-overlay.zip`

**Dependencies:** `SB-C02`, `SB-C03`, `SB-C04`, `SB-C05`. **Promotion gates:** `SB-G07`. **Targets:** `skybind`, `skybind_android_device`, `skybind_release`. **Risk:** critical. **State:** `PLANNED`.

**Retained original obligations:** `SB-O34`, `SB-O35`, `SB-O36`.

**Complete feature workstreams:**
- Whole-product fault injection, error recovery and source security test matrix.
- Physical Android arm64 root-manager, app-visibility and endurance qualification workflows.
- Reproducible NewFuture and bclone release packaging, SBOM, hashes, provenance.
- Complete source/device evidence closure and independent gate qualification support.

**Minimum negative acceptance cases:**
- No device claim from unit tests, root shell, emulation or install-only evidence.
- No release when source/destination content, app visibility or manifest identity is unverified.
- No missing negative/security cases, open critical obligations, leaked secrets or forged receipts.
- No seal if upstream pins are absent or any mandatory device condition unverified.

**Gate relationship:** `SB-G08` is a separately evaluated milestone with its own evidence ledger. This artifact installs and source-validates features; it cannot assert that gate is passed.
**Files and packages covered:** `.github/workflows`, `docs/qualification`, `docs/release`, `scripts/dev/device`, `scripts/dev/release`, `scripts/dev/release-audit`, `tests/device`, `tests/fault`, `tests/integration`, `tests/seal`, `tests/security`. A real implementation may add narrowly justified source/test paths with inventory updates, but cannot silently omit any retained obligation.
**Devtool validation:** run the targeted positive and negative tests for **every** subordinate old obligation (see appendix and JSON), impacted dependent suites, cross-target integration fixtures, security scans, source attribution and freshness; rollback on any failure. Real-device-only checks become explicit `device_unverified`, never a false pass.

### SB-CG1 — Independent Milestone Gate Definitions & Execution (G03–G08)
**Archive:** `skybind-SB-CG1-independent-milestone-gates.devtool-overlay.zip`

**Dependencies:** `SB-C06`. **Promotion gates:** none. **Targets:** `skybind_release`. **Risk:** critical. **State:** `PLANNED`.

**Retained original obligations:** `SB-G03`, `SB-G04`, `SB-G05`, `SB-G06`, `SB-G07`, `SB-G08`.

**Complete feature workstreams:**
- Fresh-process independent per-gate validation against frozen exact commit/source hashes.
- Individual promise ledgers, exported obligations, scenario matrices and blocker classification.
- Fail-closed G03/G04/G05/G06/G07/G08 promotion in dependency order.
- Carry forward blocked G01/G02 as BLOCKED without fabricating release readiness.

**Minimum negative acceptance cases:**
- Gate scripts cannot modify inspected product source.
- Stale/incomplete/skipped/device-unverified evidence never passes.
- No family-level blanket PASS based on prior reports.
- No automatic final seal issuance.

**Independent gate execution:** Implement six separate `SB-G03`…`SB-G08` gate test workflows and separately scoped promise ledgers, exported obligations, negative-test reports and fixed-point audits. The gate-only validation jobs operate on a frozen commit without changing product implementation. A failed gate does not silently fail-open because other gates pass. Dependencies must be checked per gate: G03→G04/G05→G06→G07→G08. Running the definition tests is not passing a milestone.

### SB-CFS1 — Final Skybind Whole-Product Qualification Seal
**Archive:** `skybind-SB-CFS1-final-seal.devtool-overlay.zip`

**Dependencies:** `SB-CG1`. **Promotion gates:** none. **Targets:** `skybind_release`, `skybind_android_device`. **Risk:** critical. **State:** `PLANNED`.

**Retained original obligations:** `SB-FS1`.

**Complete feature workstreams:**
- Verify source, provider/build reproducibility, WebUI parity and ALL eight gate attestations.
- Check physical Android ordinary-app file access and qualified manager/device matrix.
- Check SHA256 provenance, evidence lineage, critical obligation closure and fresh-process fixed-point audit.
- Issue cryptographically anchored/hashed final qualification report only for proven scope.

**Minimum negative acceptance cases:**
- Missing signed/pinned provider, device or security evidence blocks seal.
- Never convert an accepted definition into a passed gate.
- No seal for provisional or unknown app-visibility outcomes.

**Seal execution:** require authentic device attestations, original WebUI parity, reproducible provider artifacts, full 57-operation closure and independently passing G01–G08. Missing evidence must stop the seal and leave the repo unqualified. The seal implementation cannot patch product logic.

## Eight original milestone gates — unchanged acceptance boundaries

### SB-G01 — Foundation and static supply-chain milestone
- **Original required evidence:** Recheck authoritative contract, target graph, private path invariants, signed/pinned input authenticity where applicable, single runtime, NewFuture helper and both provider reproducibility. Verify no excluded paths/features entered new code.
- **Assurance ceiling:** SOURCE_BUILD_PASS only; device capability and FUSE usability remain NOT_ATTESTED.
- **Definition delivery:** Already installed; promotion BLOCKED pending evidence.

### SB-G02 — Typed authority and transactional configuration milestone
- **Original required evidence:** Recheck protocol/daemon owner lock, full operation registry, durable journal, proof replay/race/failure, config atomic publish/rollback and CLI parity under malformed/adversarial input.
- **Assurance ceiling:** SOURCE_CONTROL_PASS; no real Android mount, daemon boot or device inference.
- **Definition delivery:** Already installed; promotion BLOCKED pending evidence.

### SB-G03 — Mount lifecycle, recovery and resource safety milestone
- **Original required evidence:** Run real Linux helper fixture plus virtual proc/mountinfo/FUSE scenarios, PID reuse, explicit stop stability, policy/VFS/cache symlink/disk-pressure matrix and supervisor fault injection. Require bounded retries and cache ownership.
- **Assurance ceiling:** HOST_LIFECYCLE_PASS; Android app visibility remains unqualified.
- **Definition delivery:** In SB-CG1, evaluated separately.

### SB-G04 — Android namespace/platform source-safety milestone
- **Original required evidence:** Exercise protected-process scans, multi-user alias truth, safe setns planner, transactional bind ownership/rollback, module shell hooks and conservative uninstall. Require root-manager capability coverage without asserting devices not present.
- **Assurance ceiling:** ANDROID_SOURCE_PASS only; separate optional DEVICE_PROVISIONAL evidence, never a device release seal.
- **Definition delivery:** In SB-CG1, evaluated separately.

### SB-G05 — Jobs, RC, remotes and crypt security milestone
- **Original required evidence:** Cross-check scheduled due-run at-most-once, destructive sync proofs, cancellation/process owner, loopback RC credential isolation, bounded browse/config secrets, password and crypt wrapper defaults/negative cases.
- **Assurance ceiling:** BACKEND_FEATURE_PASS; network/auth/provider behavior remains fixture-qualified until a device/network run.
- **Definition delivery:** In SB-CG1, evaluated separately.

### SB-G06 — Diagnostics and dual Web transport security milestone
- **Original required evidence:** Check Doctor and support bundle secret canaries, HTTP bootstrap/session/CSRF/Origin/Host/CSP, embedded bridge request equivalence and fallback truth, source-only transport integration.
- **Assurance ceiling:** TRANSPORT_SECURITY_PASS; embedded real-manager claim remains device-pending.
- **Definition delivery:** In SB-CG1, evaluated separately.

### SB-G07 — Near-exact original WebUI UI/UX preservation milestone
- **Original required evidence:** Compare immutable original assets and adopted ones, collect screen/state/viewports/both palette screenshots, flow traces, responsive safe areas and a11y results. Review every meaningful diff/exception; audit excluded-only controls are surgically absent.
- **Assurance ceiling:** WEBUI_PARITY_PASS only with real reference baseline; if Android embedded screenshots absent, mark its device slice PENDING.
- **Definition delivery:** In SB-CG1, evaluated separately.

### SB-G08 — Whole-product source/integration and release readiness milestone
- **Original required evidence:** Run affected then full source/integration/security/reproducibility matrices, verify required real-device receipts when available; compile dependency and unresolved-blocker ledger and cryptographically identify candidate ZIPs.
- **Assurance ceiling:** CANDIDATE_READY requires all source gates; DEVICE_RELEASE_READY only with required real-device evidence and no critical blockers.
- **Definition delivery:** In SB-CG1, evaluated separately.

## API preservation — 57 operations, zero omissions

| Operation | Class | Original obligation | New delivery artifact | Original frontend consumer |
|---|---|---|---|---|
| `runtime.status` | `query` | `SB-O04` | `ALREADY_IMPLEMENTED_OR_DEFINED` | Runtime, Home |
| `provider.status` | `query` | `SB-O23` | `SB-C03` | Remotes, Mount wizard |
| `provider.remotes` | `query` | `SB-O23` | `SB-C03` | Remotes, Mount wizard |
| `provider.browse` | `query` | `SB-O23` | `SB-C03` | Remotes, Mount wizard |
| `provider.crypt.password.status` | `query` | `SB-O24` | `SB-C03` | Remotes/crypt modal, Settings |
| `provider.crypt.password.set` | `run` | `SB-O24` | `SB-C03` | Remotes/crypt modal, Settings |
| `provider.crypt.preview` | `preview` | `SB-O24` | `SB-C03` | Remotes/crypt modal, Settings |
| `provider.crypt.create` | `run` | `SB-O24` | `SB-C03` | Remotes/crypt modal, Settings |
| `provider.crypt.recovery.status` | `query` | `SB-O24` | `SB-C03` | Remotes/crypt modal, Settings |
| `config.snapshot` | `query` | `SB-O08` | `ALREADY_IMPLEMENTED_OR_DEFINED` | Mounts, wizard, rollback |
| `config.validate` | `query` | `SB-O08` | `ALREADY_IMPLEMENTED_OR_DEFINED` | Mounts, wizard, rollback |
| `config.preview` | `preview` | `SB-O08` | `ALREADY_IMPLEMENTED_OR_DEFINED` | Mounts, wizard, rollback |
| `config.apply` | `run` | `SB-O08` | `ALREADY_IMPLEMENTED_OR_DEFINED` | Mounts, wizard, rollback |
| `config.previous` | `query` | `SB-O08` | `ALREADY_IMPLEMENTED_OR_DEFINED` | Mounts, wizard, rollback |
| `config.rollback.preview` | `preview` | `SB-O08` | `ALREADY_IMPLEMENTED_OR_DEFINED` | Mounts, wizard, rollback |
| `config.rollback` | `run` | `SB-O08` | `ALREADY_IMPLEMENTED_OR_DEFINED` | Mounts, wizard, rollback |
| `mount.list` | `query` | `SB-O10` | `SB-C01` | Mounts, Home, Runtime |
| `mount.status` | `query` | `SB-O10` | `SB-C01` | Mounts, Home, Runtime |
| `mount.health` | `query` | `SB-O11` | `SB-C01` | Mounts, Home, Runtime |
| `mount.start.preview` | `preview` | `SB-O10` | `SB-C01` | Mounts, Home, Runtime |
| `mount.start` | `run` | `SB-O10` | `SB-C01` | Mounts, Home, Runtime |
| `mount.stop` | `run` | `SB-O10` | `SB-C01` | Mounts, Home, Runtime |
| `mount.restart` | `run` | `SB-O10` | `SB-C01` | Mounts, Home, Runtime |
| `mount.reconcile` | `reconcile` | `SB-O10` | `SB-C01` | Mounts, Home, Runtime |
| `policy.status` | `query` | `SB-O13` | `SB-C01` | Runtime, Mount wizard |
| `vfs.profiles` | `query` | `SB-O13` | `SB-C01` | Runtime, Mount wizard |
| `cache.status` | `query` | `SB-O14` | `SB-C01` | Runtime, Mount wizard |
| `cache.prune.preview` | `preview` | `SB-O14` | `SB-C01` | Runtime, Mount wizard |
| `cache.prune` | `run` | `SB-O14` | `SB-C01` | Runtime, Mount wizard |
| `cache.clear.preview` | `preview` | `SB-O14` | `SB-C01` | Runtime, Mount wizard |
| `cache.clear` | `run` | `SB-O14` | `SB-C01` | Runtime, Mount wizard |
| `cache.forget.preview` | `preview` | `SB-O14` | `SB-C01` | Runtime, Mount wizard |
| `cache.forget` | `run` | `SB-O14` | `SB-C01` | Runtime, Mount wizard |
| `namespace.inspect` | `query` | `SB-O15` | `SB-C02` | Runtime, Mounts, Doctor |
| `namespace.preview` | `preview` | `SB-O16` | `SB-C02` | Runtime, Mounts, Doctor |
| `namespace.apply` | `run` | `SB-O16` | `SB-C02` | Runtime, Mounts, Doctor |
| `namespace.rollback.preview` | `preview` | `SB-O17` | `SB-C02` | Runtime, Mounts, Doctor |
| `namespace.rollback` | `run` | `SB-O17` | `SB-C02` | Runtime, Mounts, Doctor |
| `namespace.reconcile` | `reconcile` | `SB-O17` | `SB-C02` | Runtime, Mounts, Doctor |
| `jobs.snapshot` | `query` | `SB-O20` | `SB-C03` | Jobs, Activity |
| `jobs.preview` | `preview` | `SB-O20` | `SB-C03` | Jobs, Activity |
| `jobs.apply` | `run` | `SB-O20` | `SB-C03` | Jobs, Activity |
| `jobs.status` | `query` | `SB-O20` | `SB-C03` | Jobs, Activity |
| `job.run.preview` | `preview` | `SB-O21` | `SB-C03` | Jobs, Activity |
| `job.run` | `run` | `SB-O21` | `SB-C03` | Jobs, Activity |
| `rc.metrics` | `query` | `SB-O22` | `SB-C03` | Runtime, Home |
| `operation.status` | `query` | `SB-O07` | `ALREADY_IMPLEMENTED_OR_DEFINED` | Activity |
| `operation.list` | `query` | `SB-O07` | `ALREADY_IMPLEMENTED_OR_DEFINED` | Activity |
| `operation.cancel` | `cancel` | `SB-O07` | `ALREADY_IMPLEMENTED_OR_DEFINED` | Activity |
| `doctor.report` | `query` | `SB-O25` | `SB-C04` | Doctor, Logs |
| `doctor.bundle` | `run` | `SB-O26` | `SB-C04` | Doctor, Logs |
| `doctor.bundle.read` | `query` | `SB-O26` | `SB-C04` | Doctor, Logs |
| `diagnostics.logs` | `query` | `SB-O25` | `SB-C04` | Doctor, Logs |
| `platform.status` | `query` | `SB-O18` | `SB-C02` | Runtime, Home |
| `ui.settings` | `query` | `SB-O32` | `SB-C05` | Settings |
| `ui.settings.preview` | `preview` | `SB-O32` | `SB-C05` | Settings |
| `ui.settings.apply` | `run` | `SB-O32` | `SB-C05` | Settings |

## Detailed contract retention: all 27 remaining implementation obligations

The descriptions, targeted tests, negative cases and promotion criteria below are carried forward from the original 45-item plan. They are a normative checklist *inside* the consolidated artifacts, not new archives.

### SB-O10 — Owned process, FUSE lifecycle and explicit desired state → `SB-C01`
**Scope:** `internal/mounts/lifecycle`, `internal/runtimeauth`, `internal/daemon`, `tests/mounts`.
**Implementation:** Implement list/status/health and start.preview/start/stop/restart/reconcile using exact pinned rclone, --config, per-mount locks/logs/cache, typed argv and process groups. Persist user desired RUNNING/STOPPED separately from observed state. Prove ownership using PID plus Linux start time, executable identity and mountinfo; graceful TERM -> identity recheck -> bounded KILL; release only owned binds and FUSE. Return bounded actionable startup errors.
**Targeted validation:** go test ./internal/mounts ./internal/runtimeauth; process-launch fixture; PID reuse, forged mountinfo, concurrent stop/reconcile, orphan children, mountpoint occupied and shutdown tests.
**Negative gate:** A stray process killed, foreign mount unmounted, explicit stop forgotten, duplicate start or unbounded error tail blocks.
**Acceptance:** Mount operations work independently without relying on PID/path existence alone.

### SB-O11 — Dependency-aware boot/readiness and health classification → `SB-C01`
**Scope:** `internal/readiness`, `internal/mounts/health`, `tests/readiness`.
**Implementation:** Construct readiness DAG for root state/privileges, package integrity, /dev/fuse, storage availability, network link/type, configured remote, startup stabilization and Android boot milestones. Define RUNNING, DEGRADED, REMOTE_OFFLINE, MOUNT_STALE, AUTH_ERROR, FUSE_ERROR, RETRYING, STOPPED with nonfabricated reason codes; expose readiness blockers independently for UI/Doctor.
**Targeted validation:** go tests and table-driven readiness-state transitions; delayed storage, unknown-metered network, absent /dev/fuse, auth/fuse distinction, partial boot fixtures.
**Negative gate:** Global sleep masquerading as readiness, remote-offline mistaken for absent mount, fake running based on PID or unrecoverable blocker classification fails.
**Acceptance:** Observed health is truthful, reason-coded, and independently consumable by the supervisor and UI.

### SB-O12 — Per-mount supervisor, recovery and bounded retry → `SB-C01`
**Scope:** `internal/supervisor`, `internal/mounts`, `internal/readiness`, `tests/recovery`.
**Implementation:** Reconcile desired versus observed state using per-mount locks; classify transport/auth/FUSE conditions, preserve useful offline VFS mounts, track persistent restart attempts and backoff/caps, reset after stability, handle daemon crash/restart, network transitions and mount staleness without violating explicit stop. Do not cascade failures between mounts.
**Targeted validation:** Fault-injection readiness/restart/crash tests, retry-budget timings, concurrent stop-vs-watch, no-duplicate-worker tests; selected Go race coverage where suitable.
**Negative gate:** Unbounded restart storm, broken explicit stop, unrelated-mount restart or unowned stale unmount blocks.
**Acceptance:** Recovery is targeted, bounded, inspectable and safe after daemon restart.

### SB-O13 — Network, power and VFS profiles → `SB-C01`
**Scope:** `internal/policy`, `internal/vfs`, `internal/mounts/config`, `tests/policy`.
**Implementation:** Implement network classes (any, Wi-Fi, unmetered, offline allowed), conservative unknown metered state, charging-only, minimum battery, min free cache, stabilization/settle policy and user-visible policy decision reasons. Expand Streaming/Balanced/Offline/Minimal/Custom VFS presets with canonical cache-mode/size/age/dir-cache/poll rules and advisory-only device recommendations. Never silently rewrite user-selected options.
**Targeted validation:** go test ./internal/policy ./internal/vfs; policy transition truth tables, profile golden cases, unknown battery/network, non-restart policy-only edit and clamp/boundary cases.
**Negative gate:** Unknown metered treated as unmetered, profiles changing in secret, invalid durations/sizes or policy change restarting healthy mount blocks.
**Acceptance:** All resource policies have deterministic decisions and existing WebUI inputs map exactly to backend values.

### SB-O14 — Owned VFS cache metrics, bounded prune/clear/forget → `SB-C01`
**Scope:** `internal/cache`, `internal/previewproof`, `internal/mounts`, `tests/cache`.
**Implementation:** Implement per-mount owned cache status, bytes/files/free/max/thresholds, aged-file pruning to low water, minimum free-space guard, clear.preview/clear, prune.preview/prune, forget.preview/forget. All destructive operations require stopped mount, exact owner/path proof, nofollow traversal, short-lived preview proof, consistent cancellation and audit journal. Keep protected files outside cache untouched.
**Targeted validation:** go test ./internal/cache; symlink swap/path traversal/root deletion, active mount refusal, cancel-safe traversal, concurrent cleanup, disk-pressure and proof replay fixtures.
**Negative gate:** Deleting a stranger file, clearing active cache, stepping through symlink, reporting nonexistent storage or partial unjournaled mutation blocks.
**Acceptance:** Cache maintenance is independently owned, bounded and safe for Android private storage.

### SB-O15 — Read-only Android namespace topology and alias facts → `SB-C02`
**Scope:** `internal/namespace/topology`, `internal/namespace/inspect`, `tests/namespace`.
**Implementation:** Bound PID/namespace scans (reference budget 4,096/512); gather mount namespace inode, group-member UID/command/user and mountinfo, classify system/service/zygote/USAP/MediaProvider/ExternalStorage/Termux/root/app scopes. Track exact target versus Android path aliases and per-user emulated storage topology. Report visible_at_target, visible_at_alias, identity_mismatch, not_visible, unavailable with confidence and evidence. Never take mutation merely from read-only discovery.
**Targeted validation:** Proc fixture matrices for work profiles/users, alias-only, same namespace multiple PIDs, incomplete proc, namespace churn, misidentified protected member; host source contract tests.
**Negative gate:** Alias treated as exact-path success, partial scan considered complete, system namespace treated as ordinary app, or default user 0 assumption blocks.
**Acceptance:** Skybind can truthfully inspect Android app visibility without touching other namespaces.

### SB-O16 — Opt-in guarded namespace bind planner and apply → `SB-C02`
**Scope:** `internal/namespace/mutation`, `internal/namespace/topology`, `internal/previewproof`, `tests/namespace`.
**Implementation:** Implement an opt-in preview that revalidates exact Skybind-owned FUSE identity, destination path, supported namespace capabilities/topology, all namespace group members, protected classes, Android user and target occupancy. Bind only to explicitly allowed same-path targets; require fresh one-use proof and a namespace-identity recheck under lock before setns/bind. Journal each applied bind and unwind newly added binds if any step fails.
**Targeted validation:** No-root planner fixtures, setns syscall mock with controlled failure at each step, stale proof/race/protected process table, containment and transactional rollback tests.
**Negative gate:** Binding into zygote/USAP/MediaProvider/ExternalStorage namespace, masking an existing mount, silent cross-user bind or partial unowned cleanup blocks.
**Acceptance:** Only provably safe explicit visibility actions are enabled; unsafe or unknown topologies return informative blocked outcomes.

### SB-O17 — Namespace bind ownership, recovery and rollback → `SB-C02`
**Scope:** `internal/namespace/reconcile`, `internal/namespace/ownership`, `tests/namespace`.
**Implementation:** Persist exact source/target mount signatures, device/user/namespace identity and intent; provide rollback.preview/rollback/reconcile. After boot/daemon restart re-read topology and compare ownership before releasing, repeating or acknowledging bind. Ignore stale namespaces without asserting success. Release owned app binds BEFORE removing owned source FUSE mount.
**Targeted validation:** Interrupted bind journal recovery, PID/namespace reuse, stale signature, foreign remount, process-churn and read-only expected-state fixtures; real-device qualification separately guarded.
**Negative gate:** Orphaned/foreign bind removal, double bind, stale mount identity, restart widening protection scope or false device certification blocks.
**Acceptance:** Namespace visibility state is durable, evidence-based and has precise cleanup semantics.

### SB-O18 — Magisk/KernelSU/APatch installation, boot and Action → `SB-C02`
**Scope:** `module/module.prop`, `module/customize.sh`, `module/post-fs-data.sh`, `module/service.sh`, `module/action.sh`, `internal/rootmgr`, `internal/platformstate`, `tests/platform`.
**Implementation:** Detect root-manager capabilities rather than names; support Magisk, KernelSU/Next, APatch and compatible module managers. Keep shell hooks thin; validate packaged runtime/manifest/modes at install, create owned private readiness marker at post-fs-data, start one locked daemon from service, reconcile via native code, and start standalone authenticated WebUI via Action/VIEW intent. Distinguish staging from post-reboot installed identity.
**Targeted validation:** sh -n/shellcheck where available, platform hook fixtures for each manager, corrupt-integrity refusal, idempotent boot, missing component, late storage and CLI/Action startup test.
**Negative gate:** Unsigned/corrupt payload accepted, service runs unsupported runtime, duplicate daemon or root manager name used as capability proof blocks.
**Acceptance:** Root modules install/start safely and remain observable across restart without duplicate lifecycle logic in shell.

### SB-O19 — Conservative uninstall and explicit purge semantics → `SB-C02`
**Scope:** `module/uninstall.sh`, `internal/platformlifecycle`, `internal/namespace`, `internal/paths`, `tests/platform`.
**Implementation:** Implement default uninstall preserving root-private configuration/cache and stopping only Skybind-owned processes, mounts, binds and transient tokens. Add explicit one-use purge-on-uninstall opt-in marker: verify mode/owner/location, nofollow paths, full source detachment and exact state boundaries before deleting. Never recursively remove arbitrary /data/adb or unrelated app/user storage. Respect interrupted cleanup/retry semantics.
**Targeted validation:** Owner/source corruption, foreign target, invalid marker, symlinked state and cache, interrupted uninstall and preserved-state fixtures; guarded real-device uninstall smoke.
**Negative gate:** Default data deletion, unowned unmount/kill, implicit purge or partial device-level wipe blocks.
**Acceptance:** Removal is safe, reversible by reinstall for retained configuration, and purge only happens with valid express authority.

### SB-O20 — Revisioned scheduled-job registry and due-run claim → `SB-C03`
**Scope:** `internal/jobs/registry`, `internal/jobs/scheduler`, `internal/previewproof`, `tests/jobs`.
**Implementation:** Implement jobs.snapshot/preview/apply/status and typed copy/sync/check definitions; bind source/destination/every, enabled and network/power policies, explicit destructive sync consent, per-job next/last/run-count state. Claim due work and persist its next occurrence BEFORE dispatch under per-job lock, guaranteeing at-most-once dispatch claim after daemon restart. Expose actions through same journal/proof engine.
**Targeted validation:** Job schema, stale revision/digest, destructive sync previews, daemon restart at due time, duplicate claim races, disabled/policy-blocked job tests.
**Negative gate:** Executing sync without consent, duplicate scheduled claim, failure to journal skipped/blocked jobs, or option-like remote endpoints blocks.
**Acceptance:** Safe scheduled-job intent and state are publishable independently of actual execution.

### SB-O21 — Managed job executor, progress and cancellation → `SB-C03`
**Scope:** `internal/jobs/executor`, `internal/journal`, `internal/runtimeauth`, `tests/jobs`.
**Implementation:** Execute only typed copy/sync/check using pinned runtime and canonical --config, with no arbitrary argv or shell. Bounded stdout/stderr and progress parsing for bytes/speed/ETA, structured terminal state, individually cancellable process groups, resource guards before/while running and per-job isolation. Manual job.run.preview/run shares scheduler safety rules; failures state clearly and never report false success.
**Targeted validation:** Fake-rclone integration, injected mid-transfer cancellation, failure stdout, concurrent jobs, process ownership, sync/destination negative and policy-transition fixtures.
**Negative gate:** Cancelling unrelated process, accidentally executing a different executable, unbounded telemetry, unconfirmed destructive sync or silent job success blocks.
**Acceptance:** Copy/sync/check are controllable, safe and accurately reflected in Activity and Jobs UI.

### SB-O22 — Per-mount authenticated loopback RC telemetry → `SB-C03`
**Scope:** `internal/rc`, `internal/mounts/lifecycle`, `tests/rc`.
**Implementation:** Start RC on 127.0.0.1 with random per-mount credentials in volatile owner-private state, assigned safe ports and lifecycle cleanup. Implement rc.metrics with allow-listed calls and bounded result projection for uptime, errors, speed, bytes, open files and VFS/cache data where supported. Differentiate unsupported/unavailable fields from zero. Never expose an RC URL, password, or generic proxy.
**Targeted validation:** Cross-instance isolation, auth failure, port collision, missing RC support, stale credential and secret-canary fixtures.
**Negative gate:** Non-loopback RC, credential in logs/UI/bundle, accepting generic method, or cross-mount metrics confusion blocks.
**Acceptance:** Each managed mount has isolated metrics with safe read-only typed projections.

### SB-O23 — Root-private remote discovery and bounded browsing → `SB-C03`
**Scope:** `internal/provider/remote`, `internal/provider/browse`, `tests/provider`.
**Implementation:** Read canonical root-private rclone.conf explicitly; expose credential-free remote inventory, type/crypt badge, list folders/files for validated remote:path only, bounded pagination/limit/path normalization and breadcrumb/parent/copy-endpoint contracts. Record remote selection provenance for mount/job form handoff; invalidate trust if user manually modifies the chosen path. Reject arbitrary unconfigured backends/option-shaped endpoints.
**Targeted validation:** Remote config secret canaries, traversal/on-the-fly syntax, invalid paths, huge directories, timeouts, plain/crypt classification and endpoint handoff tests.
**Negative gate:** Exposing private rclone.conf, shelling out with arbitrary option strings or claiming browse succeeded with incomplete results blocks.
**Acceptance:** Original remote browser can run against secure, scoped, bounded backend operations.

### SB-O24 — User-defined crypt password and safe crypt wrapper creation → `SB-C03`
**Scope:** `internal/provider/crypt`, `internal/provider/password`, `internal/previewproof`, `tests/crypt`.
**Implementation:** Support one user-supplied password via CLI stdin or secure UI field, private rclone-obscured storage, status/generation and non-secret recovery warning; never invent password, retain cleartext, set password2, or silently rekey. Preview/create a crypt wrapper through rclone with defaults filename standard, directory_name_encryption=true, filename_encoding=base32, data encryption via rclone; advanced obfuscate/off and base64/base32768 where supported. Reject nested/self crypt and partial definitions; verify result and undo only failed new definition.
**Targeted validation:** Password stdin/secret-canary scans across all outputs, wrong generation, nested crypt, option whitelist, interrupted creation, cleanup ownership and UI request-shape tests.
**Negative gate:** Cleartext in API/log/report, crypt without password, a new self-reference, promised data encryption implementation or unjustified rekey blocks.
**Acceptance:** Encryption management is correctly delegated to rclone and fits existing crypt modal without UI redesign.

### SB-O25 — Structured sanitized diagnostics and Doctor → `SB-C04`
**Scope:** `internal/diagnostics`, `internal/doctor`, `internal/control`, `tests/doctor`.
**Implementation:** Implement bounded timestamped DEBUG/INFO/WARN/ERROR logs, source/code/redaction/suppression count, byte-rotated owner-private files, query filters/follow polling and per-mount tails. Doctor produces PASS/INFO/WARN/FAIL with fixes for runtime/provenance, FUSE, platform, policies, mounts, namespaces, jobs, RC, remote/crypt, storage and WebUI. Treat expected static/read-only posture as informational rather than spurious failure.
**Targeted validation:** Log truncation/invalid UTF-8, secret canaries, severity/category/query, tampered provenance, doctor partial availability, deterministic remediation mapping tests.
**Negative gate:** A secret in logs, an unsupported function marked PASS, unbounded log query or false green due to unavailable device blocks.
**Acceptance:** Backend has a trustworthy sanitized diagnostic surface suitable for existing Doctor and Logs screens.

### SB-O26 — Owned redacted support ZIP and evidence inventory → `SB-C04`
**Scope:** `internal/doctor/support`, `internal/integrity`, `tests/support`.
**Implementation:** Assemble bounded deterministic support ZIP under root-owned diagnostics/support, with manifest and per-entry hashes: sanitized config summary, operation/health snapshots, platform identity, namespace observation, logs and reason codes. Explicitly omit tokens, rclone secrets, RC auth, user password, internal paths beyond safe summaries and unbounded file contents. doctor.bundle.read may read only correctly owned Skybind-created bounded bundles.
**Targeted validation:** Secret canary scanning of every ZIP entry, forged bundle ID/traversal, symlink root, oversized logs, partial ZIP and manifest mismatch fixtures.
**Negative gate:** Accidental private config inclusion, arbitrary file download, secret leak or success on incomplete bundle blocks.
**Acceptance:** Support export is safe, attributable and reproducible where data inputs are fixed.

### SB-O27 — Standalone loopback WebUI transport and sessions → `SB-C04`
**Scope:** `internal/webui/http`, `internal/control`, `cmd/skybind`, `module/webroot/bridge.js`, `tests/webui-transport`.
**Implementation:** Serve local assets only through IPv4 127.0.0.1 ephemeral HTTP with no-store/CSP/referrer/frame/MIME controls, one-use expiring bootstrap token, HttpOnly SameSite=Strict short-lived session, CSRF for mutating API, exact Origin/Host and request/response bounds. Route /api/v1 typed envelopes to same control engine as CLI. Expose skybind webui start/serve while keeping runtime state ephemeral and product configuration durable.
**Targeted validation:** HTTP token replay/expiry, cross-origin, CSRF/Host, XSS output, oversized body, idle-session expiry, fake route and UI backend-equivalence tests.
**Negative gate:** Binding 0.0.0.0, query-accessible arbitrary command, permissive CORS, browser RC passthrough or token leakage blocks.
**Acceptance:** Standalone UI can securely exercise existing workflows without acquiring backend privileges of its own.

### SB-O28 — Embedded root-manager bridge transport and equivalence → `SB-C04`
**Scope:** `internal/webui/bridge`, `cmd/skybind`, `module/webroot/bridge.js`, `module/action.sh`, `tests/webui-bridge`.
**Implementation:** Implement fixed skybind webui bridge entrypoint carrying base64url-encoded typed request and bounded response. Discover supported embedded APIs by observed capabilities, never by brand alone; preserve request_id/events/errors and ownership rules. Fallback to standalone only after real launch/availability proof. Test bridge exceptions, unavailable manager, version drift and equivalent visual flow.
**Targeted validation:** CLI/HTTP/embedded contract triples, malformed base64, missing API, old protocol, transport failure, root-manager capability and notification/focus regression tests.
**Negative gate:** A browser can execute privileged shell, missing bridge is treated as success, or transport changes backend behavior blocks.
**Acceptance:** Embedded and standalone views share one feature surface with identical security and UX semantics.

### SB-O29 — Direct-copy frontend shell, tokens and baseline fixture runner → `SB-C05`
**Scope:** `module/webroot/index.html`, `module/webroot/style.css`, `module/webroot/app.js`, `module/webroot/model.js`, `module/webroot/bridge.js`, `module/webroot/icon.png`, `tests/webui/fixtures`.
**Implementation:** Apply only Skybind-specific branding changes to directly reused WebUI assets; preserve all other UI/UX. Copy the checked-in reference WebUI files directly; preserve navigation Home/Mounts/Jobs/Activity/More, desktop sidebar, fixed mobile bar, topbar, badges, design tokens, dark/light mode, 760px breakpoint, motion and safe-area behavior, original local icon and assets. Delete only excluded-feature DOM/state/handlers and adapt backend calls through a tiny adapter; retain untouched reference hashes, source diff and deterministic snapshot fixture server. No framework rewrite or redesign.
**Targeted validation:** Reference SHA-256 and DOM ID/token audit, static JS checks, 360/390/412/691/759/760/1024px screenshot fixtures, both palette modes, original-vs-copy semantic diff.
**Negative gate:** Changing nav hierarchy, swapping framework/design tokens, new icon set, orphaned excluded handler, unexplained visual drift or missing golden fixture blocks.
**Acceptance:** User-recognizable UI shell is copied rather than reinterpreted and is ready for progressive backend hookup.

### SB-O30 — Home and Mounts exact interaction and wizard parity → `SB-C05`
**Scope:** `module/webroot/app.js`, `module/webroot/model.js`, `tests/webui/home-mounts`.
**Implementation:** Preserve Home hero/status, Runtime/Mounts/FUSE/Network four-card order, attention box, two quick actions, mount and activity previews and backend-authority/Refresh panel. Preserve Mounts cards/badges and contextual bottom sheet Start/Stop/Restart/Edit/Activity/Logs/Delete, config rollback and exact Source → Destination → Behavior → Review wizard: remote picker/manual entry/probe, destination suggestion, VFS/resource advanced fields, sticky navigation and proof-bound Apply. Keep focus return, error timing and unsaved-change behavior.
**Targeted validation:** Golden screenshots for normal/loading/blocked/error cases, wizard step traces and keyboard/focus audit, mocked and real Go API fixtures, stale-proof/duplicate target/password absence cases.
**Negative gate:** Different wizard step order, different action-sheet semantics, missing fields or deceptive success/errors blocks.
**Acceptance:** Home and Mounts visually and functionally match original UI with backed typed operations.

### SB-O31 — Jobs and Activity exact UI/UX parity → `SB-C05`
**Scope:** `module/webroot/app.js`, `module/webroot/model.js`, `tests/webui/jobs-activity`.
**Implementation:** Preserve existing job cards/form, enabled state, copy/sync/check type, every/policy controls, preview/confirm, last/next run, run/cancel, progress/status/ETA and error banners. Preserve Activity operation cards, grouping/order, timestamps, structured details, cancel availability and refresh/busy behaviors. Remove only historical out-of-scope controls while keeping the source styling, cards and dialog flow.
**Targeted validation:** Jobs create/edit/run/cancel/unsafe sync fixture traces, Activity event/cancellation rendering, live refresh and empty/error screenshot matrices, keyboard/screenreader checks.
**Negative gate:** Reformatting jobs as generic table, losing journal details, false cancelability, stale task display or unconfirmed sync button action blocks.
**Acceptance:** Existing Jobs and Activity remain familiar and faithfully represent durable backend state.

### SB-O32 — More, Runtime, Remotes, Doctor, Logs and Settings parity → `SB-C05`
**Scope:** `module/webroot/app.js`, `module/webroot/model.js`, `tests/webui/secondary`.
**Implementation:** Retain More cards/navigation; Runtime provenance, immutable status, per-mount/VFS/cache/RC/policy/namespace sections; Remotes chips, browse breadcrumbs, folder/item sheet, endpoint copy/handoff, crypt password status and creation modal; Doctor severity cards, fixes, support ZIP; Logs technical list with severity/source/search, follow/pause, copy/export/clear-view only; Settings grouped cards, appearance, default page, dense mode, reduced motion, refresh and session idle, limits, diagnostics/About. Align settings options with backend without silently removing visible choices.
**Targeted validation:** Per-screen reference screenshots dark/light and narrow/wide, browse/crypt modal traces, log filtering, support download, settings revision conflict and nonsecret transport tests.
**Negative gate:** Changing hierarchical navigation, deleting in-scope controls, misleading runtime capabilities, hidden credential fields or unapproved style drift blocks.
**Acceptance:** Every More subview, modal, settings control and backend feedback path is preserved.

### SB-O33 — Responsive/accessibility/end-to-end dual-transport UX qualification → `SB-C05`
**Scope:** `tests/webui/visual`, `tests/webui/interaction`, `tests/webui/a11y`, `docs/ux`.
**Implementation:** Run original-vs-recreation visual and interaction parity at 360, 390, 412, 691, 759/760 and 1024px; dark/light, dense/default, reduced motion/enlarged text, portrait/landscape, keyboard open, long paths, offline/session-expired, modal/sheet, empty/loading/failure and stale proof. Verify focus traps/return, escape/device back, live notices, aria-busy, ≥44px targets, keyboard navigation and Android safe-area. Test all retained flows through both standalone and embedded transports; exceptions require exact screenshots, reason and reviewer decision.
**Targeted validation:** Deterministic reference screenshots and diff policy, real browser scripted traces, a11y scanner plus human review; device WebView screenshots when available; explicit no-unexplained-drift audit.
**Negative gate:** No golden baseline, visually novel UI, unapproved visual/flow changes, trap regression or claiming embedded parity solely from static tests blocks.
**Acceptance:** WebUI preservation is an independently gated acceptance contract, not a theme preference.

### SB-O34 — Whole-product fault injection, security and recovery matrix → `SB-C06`
**Scope:** `tests/integration`, `tests/security`, `tests/fault`, `scripts/dev/release-audit`.
**Implementation:** Build cross-subsystem fixtures: corrupt runtime/manifest, PID reuse, state symlink swap, stale proof, race in config, mount/namespace loss, cache pressure, duplicate scheduler claim, RC credential disclosure, nested crypt, interrupted provider action, log/bundle canaries, slow HTTP clients and crash during restart/uninstall. Bind each test to a unique issue/obligation and failed-vs-fixed evidence. Add targeted plus affected-graph retest and regression freeze.
**Targeted validation:** Independent Go/Python/Node fixture suites, fuzz/sanitizer subsets, race tests, secret canary scan, integrity and source/API/full-UX closure; reproduce injected failures.
**Negative gate:** Any P00–P17 in-scope feature lacks an evidence owner/test, or any critical safety failure persists blocks.
**Acceptance:** Integration and negative safety contracts are complete before device release attempts.

### SB-O35 — Arm64 install, ordinary-app visibility and endurance qualification → `SB-C06`
**Scope:** `tests/device`, `scripts/dev/device`, `docs/qualification`, `.github/workflows`.
**Implementation:** Qualify each produced provider ZIP on actual declared supported arm64 devices, record Android fingerprint/API/kernel/SELinux/root manager/version/capabilities plus rclone/FUSE hashes. Test install, boot, Action, mount read/write from a NORMAL Android app, namespace churn, work profile if present, cold/warm reboots, multi-mount/jobs, network/doze/charging/storage/auth/fuse faults, daemon death, WebUI transports, cache, uninstall retention and explicit purge. Use Devtool device manager/ADB operations and shell/push/pull/logcat/screenshot as appropriate. If a real device is absent, mark DEVICE BLOCKED—not PASS.
**Targeted validation:** Device facts capture, per-scenario immutable receipts, attached logs/screenshots, reproducible APK helper instrumentation only when an actual test-app target exists, targeted cross-provider matrix.
**Negative gate:** A rooted shell being able to read a mount cannot substitute for ordinary-app access; an emulator/host-only result cannot claim phone/endurance pass; untested managers remain unqualified.
**Acceptance:** Supported hardware claims are backed by exact devices, both runtime variants and authentic app read/write observations.

### SB-O36 — Supply-chain audit, reproducible release and final seal implementation → `SB-C06`
**Scope:** `scripts/dev/release`, `docs/release`, `.github/workflows`, `tests/seal`.
**Implementation:** Create final evidence crosswalk binding source commit, exact Devtool run IDs, overlay history, validation reports, package hashes, ELF identities, dependency inventory, UI screenshots/interaction traces, Android device receipts and unresolved-blocker ledger. Reproduce two provider ZIPs and checksum/provenance/SBOM sidecars, sign/attest where policy actually applies (do not impose APK signing on root module ZIP), produce docs for deployment/retained state/limitations/support. Implement project FS1 checker and truthful source-only vs device-release status. Invoke Devtool native final-seal as complementary target audit, not a replacement for Skybind-specific qualification.
**Targeted validation:** Release manifests, checksum compare, clean rebuild, artifact registry verify, source-state/hash and device receipt provenance; tampered/expired/absent evidence rejection.
**Negative gate:** Any critical blocker, stale device proof, unverifiable artifact, fake seal claim, unresolved UI parity exception or unsupported manager marked supported blocks.
**Acceptance:** Release and final seal are deterministic and evidence-bound, with no false promotion from source-only gates.

## Real release qualification and immutable evidence

- Each `SB-Cxx` source application has Devtool logs and machine-readable receipts, including a list of the five sub-obligations it validated. No claims of real upstream package availability or Android device qualification may be inferred from source-only evidence.
- `SB-CG1` runs the gates independently in dependency order. All G01–G08 must meet their own evidence contract; none may inherit a PASS merely because its code was shipped in a consolidated archive.
- `SB-CFS1` is a distinct seal overlay. It verifies physical Android root-manager install/reboot/uninstall and ordinary-app exact-target read/write, FUSE process ownership, jobs/crypt/RC, credentials redaction, both WebUI transports, visual UX parity, reproducible pinned arm64 provider builds and a zero-critical-open-obligation audit.
- Gate blockers carry forward in machine-readable ledgers with explicit `blocked`, `device_unverified`, `not_yet_implemented`, or `satisfied` status and exact owning obligation; no dynamic-runtime or migration content may be imported to close one.

## Next action

**Begin `SB-C01`**, including atomic Devtool roadmap/contract-test reindexing and the entire owned FUSE lifecycle, readiness, supervisor, network/power/VFS policies, and cache safety (`SB-O10`–`SB-O14`). Its artifact must run all tests during Devtool application. Do not ask the operator for follow-up `go test`/`go vet`/manual validation commands. Independently preserve blocked G01/G02 and avoid source-to-release promotion until applicable qualification passes.

**Historical reference:** `SKYBIND_ORIGINAL_45_ITEM_ROADMAP.md` in this package is retained only as an obligation-detail reference, not as the active number of deliverables.
