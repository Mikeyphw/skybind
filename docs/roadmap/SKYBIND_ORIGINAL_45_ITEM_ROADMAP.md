# SKYBIND — Devtool Overlay Campaign

> **This document is the active implementation roadmap.** It transforms the existing P00–P17 feature plan into an ordered series of **Devtool-native overlay archives** and separately delivered gate/seal overlays. It is a PLAN: no listed implementation overlay, validation gate or final seal is represented as built, applied or passed. The complete original detailed feature specification remains in `SKYBIND_FEATURE_SPEC.md` and is normative for feature completeness.
>
> **Explicit exclusions:** no dynamic/runtime-download or runtime-selection system in the installed product; no migration, historical source-transition, backward-state migration or retrospective campaign work. NewFuture/bclone is a **build-time** provider choice only; transactional product-state recovery, Devtool transaction recovery and durable validation are in scope. **The original WebUI is copied and preserved essentially as-is** for all retained capabilities; only excluded controls, backend adapters and justified security/bug fixes may differ.

## Canonical Skybind identity (applies to every planned overlay)

**Skybind** is the sole identity for the newly created product. This is a greenfield naming contract, **not an instruction to rename or migrate an installed legacy product**. From NX-era planning material and the inspected source, retain only functionality, backend semantics, and WebUI UI/UX as references; do not propagate prior product labels into new artifacts. The upstream `rclone` executable, `rclone.conf` format, NewFuture/bclone provider names, and `fusermount3` retain their upstream identifiers.

| Surface | Required new identity |
|---|---|
| Product, WebUI title, module display | **Skybind** |
| Git repository / Go project basename | `skybind` (Go module import path selected when remote ownership is known) |
| Android module ID / manager folder | `skybind` / `/data/adb/modules/skybind/` |
| Persistent root-private state | `/data/adb/skybind/` |
| CLI / daemon | `skybind` / `skybindd` |
| Packaged native entrypoint | `system/bin/skybind` (and `skybindd` only if built as a separate executable) |
| Daemon socket | `/data/adb/skybind/run/skybindd.sock` |
| Devtool core target / satellite targets | `skybind`, `skybind_webui`, `skybind_runtime_inputs`, `skybind_android_device`, `skybind_release` |
| Overlay and gate IDs | `SB-O01`–`SB-O36`, `SB-G01`–`SB-G08`, `SB-FS1` |
| Devtool artifacts | `skybind-SB-O01-*.devtool-overlay.zip` and equivalents for gates/seal |
| Release artifacts | `skybind-android-arm64-<provider>-<version>.zip` (version/provider generated from actual build facts) |
| Log, documentation, UI labels, support bundle branding | Skybind |
| Bundled upstream engine | Keep **`system/bin/rclone`**; do not rename it to `skybind` |
| rclone config | Keep rclone's native file format and `rclone.conf` basename |

**UI preservation:** import the original WebUI files as immutable reference assets. Replace **only branding-dependent text, titles, icons or asset labels that literally identify the old product**, in addition to already-approved backend adapters, removal of excluded controls, and necessary safety/bug fixes. Preserve navigation, component hierarchy, layout, spacing, styling, copy unrelated to branding, gestures, flows and responsive behavior. Keep golden comparisons with brand-only differences explicitly annotated. A visually redesigned UI fails `SB-G07`.

**Naming validation:** `SB-O01` freezes this identity table and produces a forbidden-identifier scan; `SB-O02` registers the Devtool target names; `SB-O03` establishes directories, commands and sockets; `SB-O19` checks module metadata/hooks; `SB-O29`–`SB-O33` verify WebUI branding with parity; `SB-G01`, `SB-G07`, `SB-G08`, and `SB-FS1` each reject legacy product branding in newly emitted artifacts. For scans, **exclude quarantined read-only original-source fixtures and their immutable checksums**—those must preserve the source material intact. Do not construe any old source archive name as a new product label.

## Executive delivery contract

**Deliverable:** 36 `SB-Oxx` implementation overlays + 8 `SB-Gxx` milestone gate overlays + 1 `SB-FS1` final seal overlay = **45 individually attributable Devtool overlays**. These are ordered transactions, not a single catch-all patch. **Every overlay** has target identity, precise inventory/hashes, parent dependency set, targeted proof, negative tests, validation expectations, promotion rules, evidence ledger and clear failure disposition. Gates revalidate the dependency closure and retain a source/device assurance distinction; the final seal checks all gates and real-device evidence.

**Greenfield application model:** start from a clean new `skybind` Git repository. Preserve a read-only reference snapshot of `module/webroot/` and immutable source hashes; import its assets later without creating a new design. Do not apply the historic Repair 15 archive on top of this greenfield tree—it documents useful safety contract examples but is not a creation overlay and its source hashes expect another repository state.

**The crucial distinction:** Devtool **orchestrates and proves development actions** (overlays, build, tests, devices, history, gates, seals). `skybind`/`skybindd` **run the Skybind product**. No Devtool job, Android frontend or UI bridge is allowed to become a second privileged Skybind execution engine.

### Completion labels and promotion policy

| Label | Meaning | May promote to next? |
|---|---|---|
| `PLANNED` | Overlay described, no ZIP/evidence | No |
| `IMPLEMENTED_UNVALIDATED` | Payload exists; inventory/validation not passed | No |
| `TARGETED_PASS` | Exact local tests, static checks, manifest/preflight/finalize and negative cases passed | May enter milestone gate |
| `MILESTONE_SOURCE_PASS` | Gate dependency closure and adversarial source checks pass | Next implementation wave, **not** Android approval |
| `DEVICE_PROVISIONAL` | Limited device evidence; scenario matrix incomplete | Source work only |
| `DEVICE_QUALIFIED` | Exact device/scenario claims backed by immutable receipts | May enter device-dependent release gate |
| `CANDIDATE_READY` | All applicable source/build/UI/integration gates pass | Candidate only |
| `SEALED` | FS1 verifies applicable source, packages, devices, blocker closure and exact evidence digests | Release permitted for expressly qualified matrix |
| `BLOCKED` | Failure, mismatch, missing device, open critical obligation, stale evidence | No promotion |

Device-unavailable is `BLOCKED`/`NOT_ATTESTED` for device-required criteria, **never `PASS` by skipping**. Optional device tests are not silently made required for fast source overlays, but are mandatory for final release.

## A. Actual Devtool capabilities and how this program uses them

The design follows the uploaded Devtool source (`docs/DEVTOOL_AI_AGENT_GUIDE.md`, `docs/ARTIFACTS.md`, `docs/OVERLAY_VALIDATION.md`, `docs/POLYGLOT_TARGETS_AND_WORKFLOWS.md`, `docs/WORKFLOW_SCHEDULING_AND_PLANNING.md`, `docs/EXO_TARGET_LOCAL_JOBS.md`, `docs/FINAL_RELEASE_SEAL.md`). Features are integrated in their **real supported roles**, not used as decorative names:

| Devtool facility | Required use in this roadmap |
|---|---|
| `.devtool.toml` canonical targets | `skybind`, `skybind_webui`, `skybind_runtime_inputs`, `skybind_android_device`, `skybind_release`, plus composition group; every overlay pins target(s) |
| Target-local jobs and workflow DAGs | `job:<name>` with structured `command=[...]`, `inputs`/`outputs`, explicit `depends_on`; cross-target refs use `target:<name>#<workflow>` |
| Affected graph / scheduler / preflight | Targeted changed-input closure first; include all dependents at gates; parallel only for known, non-overlapping write scopes; lock source mutators |
| Native runners and execution environment | `go`/`command` for core, `node` for vanilla WebUI fixtures, Python for security/packaging, Termux/chroot where appropriate; ADB only when device required |
| Schema-v2 overlay inventory | `add/modify/delete`, SHA-256 for payload, `source_sha256` for modifications/deletions, exact sizes; no unlisted payload or traversal |
| Embedded JSON-v1 hooks | `before_extract`, `after_extract` source/inventory preflight; bounded validation script; `before_validation`, `after_validation`, `before_commit`, `after_commit` finalizer where useful; declared write paths/capabilities |
| Transaction apply and recovery | Atomic Devtool apply, hash conflict fail-closed, journal/backup, commit only after validations, recovery/rollback using tool state; never hand-copy payloads |
| One-shot and durable validation | Small overlays: targeted validator refs; heavy builds/device/UI suites: sequential durable sessions with named phases, checkpoints, recover/retry/revision guards/events/report |
| Target warning limits | `validation.required=true`, `expected` pass and `maximum_warnings=0` target warnings; host/infrastructure warnings separately retained and investigated |
| Test selection and profiles | Explicit per-overlay Go package tests, named Node scripts, pytest selectors, test-profile quick/safety/full/device; Go race/fuzz where appropriate |
| Matrix and resource guards | Provider NewFuture/bclone, host Linux/Termux/chroot, root manager/device/Android version, UI viewports/transports; limit workers/battery/temp/disk for long runs |
| Artifacts / bundle / history | Registered ZIPs and hashes, overlay sequence/bundles when fully dependency-qualified, `artifact list/inspect/verify`, `history/rollback` and persistent run evidence |
| Android Operations | `android capabilities/devices/doctor` and guarded shell/push/pull/logcat/screenshot; install/smoke instrumentation only for actual helper APK where present; module ZIP install via validated native scripts/root manager |
| Logging, control UI, handoff | Structured `status/plan/events/report`, validation menu, Desktop/Android Workbench/HUD on available hosts, `logs`, machine JSON and handoff with authoritative run IDs |
| Final seal and release | Devtool `final-seal --target` for configured targets plus Skybind-specific FS1 crosswalk; reproducible release ZIPs, package hashes and explicit device qualification |

**Important boundary:** APK signing, instrumentation APK lifecycle, Gradle/Maven tasks, Windows/Wine validation, hosted Python dependency publishing, generic SSH deployment, and Devtool config/state migrations are **not mandatory** for this native Go/root-module product merely because Devtool supports them. Use a tool when that overlay actually needs it. Real Android qualification may employ a dedicated instrumented helper APK, in which case the Android build/sign/install/smoke tools become relevant to that separately declared target.

## B. Overlay artifact format and transaction protocol

Every `SB-Oxx`, `SB-Gxx` and `SB-FS1` is a planned `*.devtool-overlay.zip` archive with repository-relative payload, `.devtool-artifact.json` **schema_version=2** inventory and embedded `.devtool-artifact/` scripts (metadata is not copied into the product). Do not confuse the earlier Repair 15 example's schema-v1 manifest with the preferred v2 format of this new program.

**Naming:** `skybind-SB-O01-contract-reference.devtool-overlay.zip`, `...-SB-G01-foundation-gate.devtool-overlay.zip`, `...-SB-FS1-final-seal.devtool-overlay.zip` and so forth. Keep source commits separately attributable. Publish bundle archives only for tested, order-resolved subsets and use the Devtool bundle validation strategies (`per-overlay`, `after-all`, `both`) as justified. Atomic bundles do not excuse per-entry proof or obscure which overlay introduced a fault.

**Minimum `*.zip` contents:**

```text
.devtool-artifact.json
.devtool-artifact/preflight.py        # JSON-v1 source/feature/dependency guard
.devtool-artifact/validate.py         # optional domain validator, bounded timeout
.devtool-artifact/finalize.py         # optional gate/evidence check
<only explicitly inventoried repository-relative changed files>
```

**Schema-v2 shape (illustrative template; fill actual file hashes, source hashes, executable test refs and real timeout values when constructing each ZIP):**

```json
{
  "schema_version": 2,
  "type": "overlay",
  "name": "SB-O08 — Transactional mount registry",
  "repository": { "name": "skybind" },
  "target": "skybind",
  "inventory": { "format": 1, "entries": [
    { "path": "internal/mounts/config.go", "action": "add", "sha256": "<actual 64-hex digest>", "size": 1234 },
    { "path": ".devtool.toml", "action": "modify", "source_sha256": "<actual previous 64-hex digest>", "sha256": "<actual new 64-hex digest>", "size": 5678 }
  ] },
  "apply": {
    "atomic": true,
    "conflict_policy": "fail",
    "path_policy": "repository-relative",
    "commit": { "enabled": true, "strategy": "single", "message": "SB-O08: transactional mount configuration" }
  },
  "preflight": { "phases": ["before_extract", "after_extract"], "capabilities": ["repo_read"], "write_paths": [],
    "script": { "path": ".devtool-artifact/preflight.py", "runner": "python3", "protocol": "json-v1", "sha256": "<actual digest>", "timeout_seconds": 90 } },
  "validation": { "required": true, "restore": false, "build": false, "test": false,
    "failure_action": "pause", "maximum_warnings": 0,
    "tests": [ { "ref": "sb-o08-config-go" }, { "ref": "sb-o08-config-negative" } ] }
}
```

The `validation.tests[].ref` references require **real registered Devtool test/job definitions**, added to `.devtool.toml` in the current or preceding overlay. A planned test name is not executable until registered and checked by `devtool jobs`/`plan`/`preflight`. An overlay must never pass with zero executed checks. For heavy `SB-Gxx`/`SB-FS1` workflows, use a durable sequential validation session; confirm `minimum_phase` and dependency graph before finalization.

**Preflight checker responsibilities:** exact repo identity and source digest (plus approved dependency commit lineage), required prior gate receipts and hashes, no unexpected modified/deleted tracked files, safe inventory and path policy, toolchain capability checks as relevant, and scope/forbidden-feature audits. If an expected source file does not match, stop; `overlay rebase` is for reviewed and reproducible rebases only, not a silent bypass. Preflight hooks declare only needed capabilities; note Devtool reports when network/sandbox controls are declarative rather than enforced.

**Finalizer/checker responsibilities:** before_validation assert targeted test/fixture completeness; after_validation write or collect authoritative run IDs and results; before_commit block publication on redaction/inventory/unresolved blockers; after_commit observe commit/digests only (no repository writes). All scripts emit JSON-v1 result via `DEVTOOL_HOOK_RESULT_PATH`; a structured fail must fail even if exit code is zero. Persist reports using controlled, inventoried write paths and immutable external run evidence where appropriate.

**Failure policy:** normal developer iterations use `pause` to preserve patched source, history and rollback point for inspection/repair; exceptionally risky destructive-path overlays may require immediate rollback by explicitly specified policy. Never silently mark a paused transaction validated; never commit a blocked one. `--no-validate` is forbidden in release promotion. Record target warnings separately from resource/environment warnings and require zero target warnings at gate promotion.

### Canonical operator commands (use Devtool's discovered supported spelling)

```bash
REPO=/path/to/new/skybind
ARTIFACT=/path/to/skybind-SB-O08-config.devtool-overlay.zip

devtool -r "$REPO" status --json
devtool -r "$REPO" targets --json
devtool -r "$REPO" workflows --json
devtool -r "$REPO" jobs --json
devtool -r "$REPO" plan validate --target skybind --json
devtool -r "$REPO" preflight --target skybind --workflow validate --json
devtool -r "$REPO" overlay check "$ARTIFACT" --json
devtool -r "$REPO" inspect-artifact "$ARTIFACT"
devtool -r "$REPO" validate-overlay "$ARTIFACT"
devtool -r "$REPO" apply-overlay "$ARTIFACT" --validate

# For a long phased gate, inspect the active durable session before issuing controls:
devtool -r "$REPO" validate status --json
devtool -r "$REPO" validate plan --json
devtool -r "$REPO" validate events --json
# Start/continue with selected phases through the available validated API/CLI.
# Do not invent revisions or use stale --if-revision values.

devtool -r "$REPO" artifact list --json
devtool -r "$REPO" final-seal --target skybind --strict --json
```

**Device operations:** resolve `devtool android capabilities` and `android devices` first. For Skybind root module installation use the tested native installation workflow/root-manager ZIP route rather than pretending Devtool's APK `android install` command installs flashable Magisk/KernelSU/APatch modules. Device root capability, manager feature support and ordinary-app access are separate factual checks.

## C. Wave graph and release checkpoints

```text
SB-O01 -> O02 -> O03 -> O04 -> O05 -> SB-G01
                                         |
                          O06 -> O07 -> O08 -> O09 -> SB-G02
                                                        |
                          O10 -> O11 -> O12 ----+         |
                                  O13 -> O14 --+--> SB-G03
                                                       |
              O15 -> O16 -> O17 -> O18 -> O19 -> SB-G04
                                                       |
              O20 -> O21 -> O22 ----------------+        |
              O23 -> O24 ----------------------+--> SB-G05
                                                       |
              O25 -> O26 -> O27 -> O28 -> SB-G06
                                                       |
              O29 -> O30 -> O31 -> O32 -> O33 -> SB-G07
                                                       |
              O34 -> O35 -> O36 -> SB-G08 -> SB-FS1
```

The graph is illustrative; exact dependencies are listed on every overlay below and in the accompanying JSON index. Some lanes **may** run concurrently after their prerequisites, but never when they write overlapping `.devtool.toml`, frontend files, generated manifests or release state. Gate overlays are explicitly applied/validated after implementation overlays, not mere narrative milestones.

## D. Implementation overlays — precise delivery scopes

### Wave A — Contracts, Devtool bootstrap and immutable Android build inputs

#### SB-O01 — Product contract, threat model and UI reference freeze

**Covers:** P00, P16 · **Depends on:** clean repository baseline · **Target(s):** `skybind`, `skybind_webui`.

**Allowed primary file scopes:** `docs/architecture`, `docs/contracts`, `tests/contracts`, `tests/fixtures/webui-reference`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Freeze build-time NewFuture/bclone selection, root-private state, single bundled executable and FUSE-helper layout; enumerate every feature/operation/state/API error; record threat boundaries, Android capability truth, independent source-vs-device assurance and explicit exclusions. Freeze Skybind-wide identifiers (repository/module/CLI/daemon/WebUI/state/Devtool/release/overlay IDs) and a forbidden-legacy-name scan. Snapshot original module/webroot assets unmodified with SHA-256, DOM inventory, golden screen/state/interaction cases and visual-baseline manifest. List every retained and excluded UI control, and never import historical dynamic-runtime or migration behavior.

**Targeted validation / evidence:** Schema inventory, baseline hash verifier, static forbidden-feature grep, 57-operation coverage check, freeze verification, threat-case traceability.

**Mandatory negative gate:** A legacy Skybind product identifier or an omitted retained UI control, a UI hash mismatch, an orphaned operation, or an excluded historical feature fails the contract. Baseline snapshots must be genuinely captured or marked missing, never invented.

**Promotion criterion:** A current-product specification, frozen UI reference and immutable operation/feature checklist exist; all later overlays can resolve against exact baselines.

**Devtool deliverable:** `SB-O01.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

#### SB-O02 — First-class Devtool targets, graph, workflows and fixtures

**Covers:** P01, P17 · **Depends on:** SB-O01 · **Target(s):** `skybind`, `skybind_webui`, `skybind_runtime_inputs`, `skybind_android_device`, `skybind_release`.

**Allowed primary file scopes:** `.devtool.toml`, `scripts/devtool`, `tests/devtool`, `docs/development`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Declare canonical targets, target-local read-only test jobs, cross-target build jobs, named workflows, release groups, path inputs/outputs, safe parallel scheduler limits, wrapper commands, target/runner/execution-environment identities, targeted validation recipes and Android-provider detection. Distinguish source-only, build, host integration, real-device and release gates. Register baseline/parity fixtures and a project-specific seal check. Keep Devtool as orchestrator: no duplicate test scheduler, overlay engine or invented validation state machine.

**Targeted validation / evidence:** devtool config/targets/groups/jobs/workflows/plan/preflight/doctor checks; invalid target reference, write-scope escape, conflicting output, absent interpreter and toolchain-negative fixtures.

**Mandatory negative gate:** Missing named workflow, unknown dependency, unsafe parallel output overlap, phantom Android device, or zero executed validation checks blocks.

**Promotion criterion:** The rebuilt repo is natively understood by Devtool and has machine-readable dependency/affected graphs and reproducible targeted test selection.

**Devtool deliverable:** `SB-O02.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

#### SB-O03 — Go skeleton and root-private filesystem invariants

**Covers:** P01 · **Depends on:** SB-O02 · **Target(s):** `skybind`.

**Allowed primary file scopes:** `go.mod`, `cmd/skybind`, `internal/paths`, `internal/buildinfo`, `internal/atomicfile`, `tests/fixtures`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Create Go commands and package boundaries, canonical /data/adb/modules/skybind and /data/adb/skybind paths, separate immutable module bytes from retained state, owner-only 0700 dirs/0600 secrets, nofollow checks, lock/atomic write/fsync helpers and injectable filesystem adapter for non-root test fixtures only. Define run/socket, configuration, desired state, health, jobs, namespace, cache, logs, RC, UI settings and support paths. Compile Android arm64 and Linux fixture targets.

**Targeted validation / evidence:** go test ./internal/paths ./internal/atomicfile ./cmd/skybind; Go cross-compile; host fixtures for permissions, symlink traversal, partial writes and owner mismatch.

**Mandatory negative gate:** A symlinked state root, group-readable secret, invalid absolute path, platform override on a privileged build, or partial publication must be rejected.

**Promotion criterion:** Private state and executable skeleton are deterministic, testable without root, and fail closed on unsafe layouts.

**Devtool deliverable:** `SB-O03.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

#### SB-O04 — Pinned NewFuture executable and canonical FUSE helper

**Covers:** P02 · **Depends on:** SB-O03 · **Target(s):** `skybind_runtime_inputs`, `skybind`.

**Allowed primary file scopes:** `scripts/dev/runtime/newfuture`, `internal/runtimeauth`, `internal/integrity`, `module/system`, `docs/build`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Acquire the exact official NewFuture arm64 package with pinned digest; safely extract one system/bin/rclone and the official system/vendor/bin/fusermount3 plus required libfuse siblings. Implement source/ELF/mode/hash/provenance verifier and strictly canonical runtime resolver. Never search PATH or use untrusted runtime overrides. Package deterministically without executing the target binary on the host.

**Targeted validation / evidence:** Provider acquisition fixtures, archive path/symlink bombs, ELF ABI and hash tests; one-runtime binary inventory; reproducible ZIP comparison; go test ./internal/runtimeauth ./internal/integrity.

**Mandatory negative gate:** Two executables, untrusted helper origin, helper from bclone, modified bytes, PATH hijack, corrupt manifest or nondeterministic archive blocks.

**Promotion criterion:** A locally reproducible NewFuture arm64 artifact with independently attested helper provenance and an operational read-only status contract.

**Devtool deliverable:** `SB-O04.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

#### SB-O05 — Pinned bclone compile and two-provider package parity

**Covers:** P02 · **Depends on:** SB-O04 · **Target(s):** `skybind_runtime_inputs`, `skybind`.

**Allowed primary file scopes:** `scripts/dev/runtime/bclone`, `scripts/dev/build_skybind.py`, `scripts/dev/package`, `tests/package`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Build bclone from an immutable commit with pinned Android NDK and explicit arm64/ABI flags. Select exactly one rclone-family executable at ZIP build time; obtain the unchanged helper/library family from NewFuture. Produce canonical runtime.provenance.json, package/SBOM inventory, deterministic timestamp/order/modes, checksum files and release diagnostics. Verify build reproducibility and effective executable identity for both provider variants.

**Targeted validation / evidence:** NDK/toolchain/provenance checks, two clean-build byte comparisons per provider, one-rclone invariant, artifact verification, helper equality fixture and corruption/negative tests.

**Mandatory negative gate:** Provider mismatch, unsupported GOARCH/ELF, missing library, second runtime, unpinned commit, manifest drift or unverifiable supply chain fails.

**Promotion criterion:** Both build-time variants are reproducible and can be differentiated by immutable provenance while sharing the canonical NewFuture helper.

**Devtool deliverable:** `SB-O05.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

### Wave B — Typed control authority, journal and configuration

#### SB-O06 — Versioned typed protocol, Unix socket and daemon authority

**Covers:** P03 · **Depends on:** SB-G01 · **Target(s):** `skybind`.

**Allowed primary file scopes:** `internal/protocol`, `internal/control`, `internal/daemon`, `cmd/skybind`, `tests/protocol`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Implement one root-owned skybindd Unix socket with exclusive daemon lock, request_id and schema_version, client protocol min/max negotiation, classes query/preview/run/cancel/reconcile, strict allow-listed operation descriptors, bounded JSON requests/responses/events and stable categories/stages/retryability. skybind supports version, capabilities, rpc, daemon and machine-friendly event streams. Restrict local fallback to identical authorization semantics.

**Targeted validation / evidence:** go test ./internal/protocol ./internal/control ./internal/daemon; fuzz invalid envelopes and unknown fields; Linux socket permission/locking tests; CLI golden JSON/NDJSON.

**Mandatory negative gate:** Unknown operation, generic shell/RC/file primitive, oversized envelope, multiple daemon owners, unsupported version or unbounded stream fails.

**Promotion criterion:** CLI and daemon use a single typed engine with deterministic errors, no arbitrary command execution and no transport-specific authority drift.

**Devtool deliverable:** `SB-O06.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

#### SB-O07 — Durable operations, cancellations and one-use proofs

**Covers:** P03, P04 · **Depends on:** SB-O06 · **Target(s):** `skybind`.

**Allowed primary file scopes:** `internal/journal`, `internal/previewproof`, `internal/control`, `tests/transactions`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Journal each operation before effects; persist structured progress, process identity, owner, timestamps, terminal outcome and interrupted-on-crash status. Implement cancellation only at approved boundaries. Issue typed digest/revision/action/subject-bound expiring single-use confirmation proofs, consumed atomically under resource locks; keep non-cancellable commit spans intact and expose list/status/cancel.

**Targeted validation / evidence:** Journal crash/restart replay fixtures, simultaneous cancellation, proof double-spend/expiry/revision swap tests, event-stream bounds and secret-canary scans.

**Mandatory negative gate:** Lost work history, acceptance of a replayed/stale proof, cancellation during atomic commit, forged request owner or leaked secret blocks.

**Promotion criterion:** Mutation tracking and proof semantics support every later transactional domain and the existing Activity UI.

**Devtool deliverable:** `SB-O07.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

#### SB-O08 — Transactional mount registry, diff and rollback

**Covers:** P04 · **Depends on:** SB-O07 · **Target(s):** `skybind`.

**Allowed primary file scopes:** `internal/mounts/config`, `internal/previewproof`, `internal/paths`, `tests/config`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Implement config registry-v2.json and previous-v2.json with canonical digest, revision, strict fields, normalized remote/destination, nested-target/private-path guards, network/power/VFS/cache settings, trusted server-only args_file and public has_args_file. Provide snapshot/validate/preview/apply/previous/rollback.preview/rollback; plan precise mount/policy/cache/namespace consequences. Atomically fsync/publish and rollback as a NEW revision with no unnecessary restart for policy-only edits.

**Targeted validation / evidence:** go test ./internal/mounts ./internal/previewproof; config golden matrices; interrupted atomic-write and previous-good tests; stale/digest/race/secret cases.

**Mandatory negative gate:** Duplicate/overlapping targets, arbitrary flags/browser args_file, wrong revision, drifted candidate or partial state blocks; unrelated mounts remain unchanged.

**Promotion criterion:** Existing WebUI configuration wizard can use a stable preview/apply/rollback protocol without altering its flow.

**Devtool deliverable:** `SB-O08.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

#### SB-O09 — Complete CLI parity and API inventory lock

**Covers:** P03, P04 · **Depends on:** SB-O08 · **Target(s):** `skybind`.

**Allowed primary file scopes:** `cmd/skybind`, `internal/control`, `docs/contracts/operations`, `tests/cli`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Expose the complete typed operation catalog with classes, argument schemas, response fixtures, stable errors, client capability discovery and CLI shorthand matching backend effects. Generate/test a machine-readable API inventory mapped to all original in-scope UI handlers, including future operations as declared yet unsupported capabilities until their overlays land. No fake-success stub may be exposed as operational.

**Targeted validation / evidence:** Typed schema/test inventory, request envelope golden vectors, CLI/daemon equivalence fixtures, requiredOperations crosswalk, capability/version negative tests.

**Mandatory negative gate:** An advertised nonimplemented operation, mismatched CLI vs daemon response, unspecified cancellation capability or silently accepted extra field blocks.

**Promotion criterion:** Every current-scope operation is enumerated and versioned; implemented subset is truthful and safely extendable by subsequent overlays.

**Devtool deliverable:** `SB-O09.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

### Wave C — Mount lifecycle, recovery, policies and cache

#### SB-O10 — Owned process, FUSE lifecycle and explicit desired state

**Covers:** P05 · **Depends on:** SB-G02 · **Target(s):** `skybind`.

**Allowed primary file scopes:** `internal/mounts/lifecycle`, `internal/runtimeauth`, `internal/daemon`, `tests/mounts`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Implement list/status/health and start.preview/start/stop/restart/reconcile using exact pinned rclone, --config, per-mount locks/logs/cache, typed argv and process groups. Persist user desired RUNNING/STOPPED separately from observed state. Prove ownership using PID plus Linux start time, executable identity and mountinfo; graceful TERM -> identity recheck -> bounded KILL; release only owned binds and FUSE. Return bounded actionable startup errors.

**Targeted validation / evidence:** go test ./internal/mounts ./internal/runtimeauth; process-launch fixture; PID reuse, forged mountinfo, concurrent stop/reconcile, orphan children, mountpoint occupied and shutdown tests.

**Mandatory negative gate:** A stray process killed, foreign mount unmounted, explicit stop forgotten, duplicate start or unbounded error tail blocks.

**Promotion criterion:** Mount operations work independently without relying on PID/path existence alone.

**Devtool deliverable:** `SB-O10.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

#### SB-O11 — Dependency-aware boot/readiness and health classification

**Covers:** P06 · **Depends on:** SB-O10 · **Target(s):** `skybind`.

**Allowed primary file scopes:** `internal/readiness`, `internal/mounts/health`, `tests/readiness`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Construct readiness DAG for root state/privileges, package integrity, /dev/fuse, storage availability, network link/type, configured remote, startup stabilization and Android boot milestones. Define RUNNING, DEGRADED, REMOTE_OFFLINE, MOUNT_STALE, AUTH_ERROR, FUSE_ERROR, RETRYING, STOPPED with nonfabricated reason codes; expose readiness blockers independently for UI/Doctor.

**Targeted validation / evidence:** go tests and table-driven readiness-state transitions; delayed storage, unknown-metered network, absent /dev/fuse, auth/fuse distinction, partial boot fixtures.

**Mandatory negative gate:** Global sleep masquerading as readiness, remote-offline mistaken for absent mount, fake running based on PID or unrecoverable blocker classification fails.

**Promotion criterion:** Observed health is truthful, reason-coded, and independently consumable by the supervisor and UI.

**Devtool deliverable:** `SB-O11.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

#### SB-O12 — Per-mount supervisor, recovery and bounded retry

**Covers:** P06 · **Depends on:** SB-O11 · **Target(s):** `skybind`.

**Allowed primary file scopes:** `internal/supervisor`, `internal/mounts`, `internal/readiness`, `tests/recovery`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Reconcile desired versus observed state using per-mount locks; classify transport/auth/FUSE conditions, preserve useful offline VFS mounts, track persistent restart attempts and backoff/caps, reset after stability, handle daemon crash/restart, network transitions and mount staleness without violating explicit stop. Do not cascade failures between mounts.

**Targeted validation / evidence:** Fault-injection readiness/restart/crash tests, retry-budget timings, concurrent stop-vs-watch, no-duplicate-worker tests; selected Go race coverage where suitable.

**Mandatory negative gate:** Unbounded restart storm, broken explicit stop, unrelated-mount restart or unowned stale unmount blocks.

**Promotion criterion:** Recovery is targeted, bounded, inspectable and safe after daemon restart.

**Devtool deliverable:** `SB-O12.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

#### SB-O13 — Network, power and VFS profiles

**Covers:** P09 · **Depends on:** SB-O11 · **Target(s):** `skybind`.

**Allowed primary file scopes:** `internal/policy`, `internal/vfs`, `internal/mounts/config`, `tests/policy`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Implement network classes (any, Wi-Fi, unmetered, offline allowed), conservative unknown metered state, charging-only, minimum battery, min free cache, stabilization/settle policy and user-visible policy decision reasons. Expand Streaming/Balanced/Offline/Minimal/Custom VFS presets with canonical cache-mode/size/age/dir-cache/poll rules and advisory-only device recommendations. Never silently rewrite user-selected options.

**Targeted validation / evidence:** go test ./internal/policy ./internal/vfs; policy transition truth tables, profile golden cases, unknown battery/network, non-restart policy-only edit and clamp/boundary cases.

**Mandatory negative gate:** Unknown metered treated as unmetered, profiles changing in secret, invalid durations/sizes or policy change restarting healthy mount blocks.

**Promotion criterion:** All resource policies have deterministic decisions and existing WebUI inputs map exactly to backend values.

**Devtool deliverable:** `SB-O13.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

#### SB-O14 — Owned VFS cache metrics, bounded prune/clear/forget

**Covers:** P09 · **Depends on:** SB-O13 · **Target(s):** `skybind`.

**Allowed primary file scopes:** `internal/cache`, `internal/previewproof`, `internal/mounts`, `tests/cache`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Implement per-mount owned cache status, bytes/files/free/max/thresholds, aged-file pruning to low water, minimum free-space guard, clear.preview/clear, prune.preview/prune, forget.preview/forget. All destructive operations require stopped mount, exact owner/path proof, nofollow traversal, short-lived preview proof, consistent cancellation and audit journal. Keep protected files outside cache untouched.

**Targeted validation / evidence:** go test ./internal/cache; symlink swap/path traversal/root deletion, active mount refusal, cancel-safe traversal, concurrent cleanup, disk-pressure and proof replay fixtures.

**Mandatory negative gate:** Deleting a stranger file, clearing active cache, stepping through symlink, reporting nonexistent storage or partial unjournaled mutation blocks.

**Promotion criterion:** Cache maintenance is independently owned, bounded and safe for Android private storage.

**Devtool deliverable:** `SB-O14.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

### Wave D — Android namespace safety and root-manager lifecycle

#### SB-O15 — Read-only Android namespace topology and alias facts

**Covers:** P07 · **Depends on:** SB-G03 · **Target(s):** `skybind`, `skybind_android_device`.

**Allowed primary file scopes:** `internal/namespace/topology`, `internal/namespace/inspect`, `tests/namespace`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Bound PID/namespace scans (reference budget 4,096/512); gather mount namespace inode, group-member UID/command/user and mountinfo, classify system/service/zygote/USAP/MediaProvider/ExternalStorage/Termux/root/app scopes. Track exact target versus Android path aliases and per-user emulated storage topology. Report visible_at_target, visible_at_alias, identity_mismatch, not_visible, unavailable with confidence and evidence. Never take mutation merely from read-only discovery.

**Targeted validation / evidence:** Proc fixture matrices for work profiles/users, alias-only, same namespace multiple PIDs, incomplete proc, namespace churn, misidentified protected member; host source contract tests.

**Mandatory negative gate:** Alias treated as exact-path success, partial scan considered complete, system namespace treated as ordinary app, or default user 0 assumption blocks.

**Promotion criterion:** Skybind can truthfully inspect Android app visibility without touching other namespaces.

**Devtool deliverable:** `SB-O15.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

#### SB-O16 — Opt-in guarded namespace bind planner and apply

**Covers:** P08 · **Depends on:** SB-O15 · **Target(s):** `skybind`, `skybind_android_device`.

**Allowed primary file scopes:** `internal/namespace/mutation`, `internal/namespace/topology`, `internal/previewproof`, `tests/namespace`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Implement an opt-in preview that revalidates exact Skybind-owned FUSE identity, destination path, supported namespace capabilities/topology, all namespace group members, protected classes, Android user and target occupancy. Bind only to explicitly allowed same-path targets; require fresh one-use proof and a namespace-identity recheck under lock before setns/bind. Journal each applied bind and unwind newly added binds if any step fails.

**Targeted validation / evidence:** No-root planner fixtures, setns syscall mock with controlled failure at each step, stale proof/race/protected process table, containment and transactional rollback tests.

**Mandatory negative gate:** Binding into zygote/USAP/MediaProvider/ExternalStorage namespace, masking an existing mount, silent cross-user bind or partial unowned cleanup blocks.

**Promotion criterion:** Only provably safe explicit visibility actions are enabled; unsafe or unknown topologies return informative blocked outcomes.

**Devtool deliverable:** `SB-O16.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

#### SB-O17 — Namespace bind ownership, recovery and rollback

**Covers:** P08 · **Depends on:** SB-O16 · **Target(s):** `skybind`, `skybind_android_device`.

**Allowed primary file scopes:** `internal/namespace/reconcile`, `internal/namespace/ownership`, `tests/namespace`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Persist exact source/target mount signatures, device/user/namespace identity and intent; provide rollback.preview/rollback/reconcile. After boot/daemon restart re-read topology and compare ownership before releasing, repeating or acknowledging bind. Ignore stale namespaces without asserting success. Release owned app binds BEFORE removing owned source FUSE mount.

**Targeted validation / evidence:** Interrupted bind journal recovery, PID/namespace reuse, stale signature, foreign remount, process-churn and read-only expected-state fixtures; real-device qualification separately guarded.

**Mandatory negative gate:** Orphaned/foreign bind removal, double bind, stale mount identity, restart widening protection scope or false device certification blocks.

**Promotion criterion:** Namespace visibility state is durable, evidence-based and has precise cleanup semantics.

**Devtool deliverable:** `SB-O17.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

#### SB-O18 — Magisk/KernelSU/APatch installation, boot and Action

**Covers:** P14 · **Depends on:** SB-O17, SB-O05 · **Target(s):** `skybind`, `skybind_android_device`.

**Allowed primary file scopes:** `module/module.prop`, `module/customize.sh`, `module/post-fs-data.sh`, `module/service.sh`, `module/action.sh`, `internal/rootmgr`, `internal/platformstate`, `tests/platform`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Detect root-manager capabilities rather than names; support Magisk, KernelSU/Next, APatch and compatible module managers. Keep shell hooks thin; validate packaged runtime/manifest/modes at install, create owned private readiness marker at post-fs-data, start one locked daemon from service, reconcile via native code, and start standalone authenticated WebUI via Action/VIEW intent. Distinguish staging from post-reboot installed identity.

**Targeted validation / evidence:** sh -n/shellcheck where available, platform hook fixtures for each manager, corrupt-integrity refusal, idempotent boot, missing component, late storage and CLI/Action startup test.

**Mandatory negative gate:** Unsigned/corrupt payload accepted, service runs unsupported runtime, duplicate daemon or root manager name used as capability proof blocks.

**Promotion criterion:** Root modules install/start safely and remain observable across restart without duplicate lifecycle logic in shell.

**Devtool deliverable:** `SB-O18.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

#### SB-O19 — Conservative uninstall and explicit purge semantics

**Covers:** P14 · **Depends on:** SB-O18 · **Target(s):** `skybind`, `skybind_android_device`.

**Allowed primary file scopes:** `module/uninstall.sh`, `internal/platformlifecycle`, `internal/namespace`, `internal/paths`, `tests/platform`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Implement default uninstall preserving root-private configuration/cache and stopping only Skybind-owned processes, mounts, binds and transient tokens. Add explicit one-use purge-on-uninstall opt-in marker: verify mode/owner/location, nofollow paths, full source detachment and exact state boundaries before deleting. Never recursively remove arbitrary /data/adb or unrelated app/user storage. Respect interrupted cleanup/retry semantics.

**Targeted validation / evidence:** Owner/source corruption, foreign target, invalid marker, symlinked state and cache, interrupted uninstall and preserved-state fixtures; guarded real-device uninstall smoke.

**Mandatory negative gate:** Default data deletion, unowned unmount/kill, implicit purge or partial device-level wipe blocks.

**Promotion criterion:** Removal is safe, reversible by reinstall for retained configuration, and purge only happens with valid express authority.

**Devtool deliverable:** `SB-O19.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

### Wave E — Jobs, metrics, remote browsing and crypt

#### SB-O20 — Revisioned scheduled-job registry and due-run claim

**Covers:** P10 · **Depends on:** SB-G03, SB-O07 · **Target(s):** `skybind`.

**Allowed primary file scopes:** `internal/jobs/registry`, `internal/jobs/scheduler`, `internal/previewproof`, `tests/jobs`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Implement jobs.snapshot/preview/apply/status and typed copy/sync/check definitions; bind source/destination/every, enabled and network/power policies, explicit destructive sync consent, per-job next/last/run-count state. Claim due work and persist its next occurrence BEFORE dispatch under per-job lock, guaranteeing at-most-once dispatch claim after daemon restart. Expose actions through same journal/proof engine.

**Targeted validation / evidence:** Job schema, stale revision/digest, destructive sync previews, daemon restart at due time, duplicate claim races, disabled/policy-blocked job tests.

**Mandatory negative gate:** Executing sync without consent, duplicate scheduled claim, failure to journal skipped/blocked jobs, or option-like remote endpoints blocks.

**Promotion criterion:** Safe scheduled-job intent and state are publishable independently of actual execution.

**Devtool deliverable:** `SB-O20.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

#### SB-O21 — Managed job executor, progress and cancellation

**Covers:** P10 · **Depends on:** SB-O20 · **Target(s):** `skybind`.

**Allowed primary file scopes:** `internal/jobs/executor`, `internal/journal`, `internal/runtimeauth`, `tests/jobs`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Execute only typed copy/sync/check using pinned runtime and canonical --config, with no arbitrary argv or shell. Bounded stdout/stderr and progress parsing for bytes/speed/ETA, structured terminal state, individually cancellable process groups, resource guards before/while running and per-job isolation. Manual job.run.preview/run shares scheduler safety rules; failures state clearly and never report false success.

**Targeted validation / evidence:** Fake-rclone integration, injected mid-transfer cancellation, failure stdout, concurrent jobs, process ownership, sync/destination negative and policy-transition fixtures.

**Mandatory negative gate:** Cancelling unrelated process, accidentally executing a different executable, unbounded telemetry, unconfirmed destructive sync or silent job success blocks.

**Promotion criterion:** Copy/sync/check are controllable, safe and accurately reflected in Activity and Jobs UI.

**Devtool deliverable:** `SB-O21.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

#### SB-O22 — Per-mount authenticated loopback RC telemetry

**Covers:** P11 · **Depends on:** SB-O10, SB-O21 · **Target(s):** `skybind`.

**Allowed primary file scopes:** `internal/rc`, `internal/mounts/lifecycle`, `tests/rc`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Start RC on 127.0.0.1 with random per-mount credentials in volatile owner-private state, assigned safe ports and lifecycle cleanup. Implement rc.metrics with allow-listed calls and bounded result projection for uptime, errors, speed, bytes, open files and VFS/cache data where supported. Differentiate unsupported/unavailable fields from zero. Never expose an RC URL, password, or generic proxy.

**Targeted validation / evidence:** Cross-instance isolation, auth failure, port collision, missing RC support, stale credential and secret-canary fixtures.

**Mandatory negative gate:** Non-loopback RC, credential in logs/UI/bundle, accepting generic method, or cross-mount metrics confusion blocks.

**Promotion criterion:** Each managed mount has isolated metrics with safe read-only typed projections.

**Devtool deliverable:** `SB-O22.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

#### SB-O23 — Root-private remote discovery and bounded browsing

**Covers:** P12 · **Depends on:** SB-O07, SB-O09 · **Target(s):** `skybind`.

**Allowed primary file scopes:** `internal/provider/remote`, `internal/provider/browse`, `tests/provider`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Read canonical root-private rclone.conf explicitly; expose credential-free remote inventory, type/crypt badge, list folders/files for validated remote:path only, bounded pagination/limit/path normalization and breadcrumb/parent/copy-endpoint contracts. Record remote selection provenance for mount/job form handoff; invalidate trust if user manually modifies the chosen path. Reject arbitrary unconfigured backends/option-shaped endpoints.

**Targeted validation / evidence:** Remote config secret canaries, traversal/on-the-fly syntax, invalid paths, huge directories, timeouts, plain/crypt classification and endpoint handoff tests.

**Mandatory negative gate:** Exposing private rclone.conf, shelling out with arbitrary option strings or claiming browse succeeded with incomplete results blocks.

**Promotion criterion:** Original remote browser can run against secure, scoped, bounded backend operations.

**Devtool deliverable:** `SB-O23.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

#### SB-O24 — User-defined crypt password and safe crypt wrapper creation

**Covers:** P12 · **Depends on:** SB-O23 · **Target(s):** `skybind`, `skybind_webui`.

**Allowed primary file scopes:** `internal/provider/crypt`, `internal/provider/password`, `internal/previewproof`, `tests/crypt`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Support one user-supplied password via CLI stdin or secure UI field, private rclone-obscured storage, status/generation and non-secret recovery warning; never invent password, retain cleartext, set password2, or silently rekey. Preview/create a crypt wrapper through rclone with defaults filename standard, directory_name_encryption=true, filename_encoding=base32, data encryption via rclone; advanced obfuscate/off and base64/base32768 where supported. Reject nested/self crypt and partial definitions; verify result and undo only failed new definition.

**Targeted validation / evidence:** Password stdin/secret-canary scans across all outputs, wrong generation, nested crypt, option whitelist, interrupted creation, cleanup ownership and UI request-shape tests.

**Mandatory negative gate:** Cleartext in API/log/report, crypt without password, a new self-reference, promised data encryption implementation or unjustified rekey blocks.

**Promotion criterion:** Encryption management is correctly delegated to rclone and fits existing crypt modal without UI redesign.

**Devtool deliverable:** `SB-O24.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

### Wave F — Diagnostics, support exports and secure WebUI transport

#### SB-O25 — Structured sanitized diagnostics and Doctor

**Covers:** P13 · **Depends on:** SB-G05, SB-G04 · **Target(s):** `skybind`.

**Allowed primary file scopes:** `internal/diagnostics`, `internal/doctor`, `internal/control`, `tests/doctor`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Implement bounded timestamped DEBUG/INFO/WARN/ERROR logs, source/code/redaction/suppression count, byte-rotated owner-private files, query filters/follow polling and per-mount tails. Doctor produces PASS/INFO/WARN/FAIL with fixes for runtime/provenance, FUSE, platform, policies, mounts, namespaces, jobs, RC, remote/crypt, storage and WebUI. Treat expected static/read-only posture as informational rather than spurious failure.

**Targeted validation / evidence:** Log truncation/invalid UTF-8, secret canaries, severity/category/query, tampered provenance, doctor partial availability, deterministic remediation mapping tests.

**Mandatory negative gate:** A secret in logs, an unsupported function marked PASS, unbounded log query or false green due to unavailable device blocks.

**Promotion criterion:** Backend has a trustworthy sanitized diagnostic surface suitable for existing Doctor and Logs screens.

**Devtool deliverable:** `SB-O25.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

#### SB-O26 — Owned redacted support ZIP and evidence inventory

**Covers:** P13 · **Depends on:** SB-O25 · **Target(s):** `skybind`.

**Allowed primary file scopes:** `internal/doctor/support`, `internal/integrity`, `tests/support`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Assemble bounded deterministic support ZIP under root-owned diagnostics/support, with manifest and per-entry hashes: sanitized config summary, operation/health snapshots, platform identity, namespace observation, logs and reason codes. Explicitly omit tokens, rclone secrets, RC auth, user password, internal paths beyond safe summaries and unbounded file contents. doctor.bundle.read may read only correctly owned Skybind-created bounded bundles.

**Targeted validation / evidence:** Secret canary scanning of every ZIP entry, forged bundle ID/traversal, symlink root, oversized logs, partial ZIP and manifest mismatch fixtures.

**Mandatory negative gate:** Accidental private config inclusion, arbitrary file download, secret leak or success on incomplete bundle blocks.

**Promotion criterion:** Support export is safe, attributable and reproducible where data inputs are fixed.

**Devtool deliverable:** `SB-O26.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

#### SB-O27 — Standalone loopback WebUI transport and sessions

**Covers:** P15 · **Depends on:** SB-O25, SB-O09 · **Target(s):** `skybind`, `skybind_webui`.

**Allowed primary file scopes:** `internal/webui/http`, `internal/control`, `cmd/skybind`, `module/webroot/bridge.js`, `tests/webui-transport`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Serve local assets only through IPv4 127.0.0.1 ephemeral HTTP with no-store/CSP/referrer/frame/MIME controls, one-use expiring bootstrap token, HttpOnly SameSite=Strict short-lived session, CSRF for mutating API, exact Origin/Host and request/response bounds. Route /api/v1 typed envelopes to same control engine as CLI. Expose skybind webui start/serve while keeping runtime state ephemeral and product configuration durable.

**Targeted validation / evidence:** HTTP token replay/expiry, cross-origin, CSRF/Host, XSS output, oversized body, idle-session expiry, fake route and UI backend-equivalence tests.

**Mandatory negative gate:** Binding 0.0.0.0, query-accessible arbitrary command, permissive CORS, browser RC passthrough or token leakage blocks.

**Promotion criterion:** Standalone UI can securely exercise existing workflows without acquiring backend privileges of its own.

**Devtool deliverable:** `SB-O27.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

#### SB-O28 — Embedded root-manager bridge transport and equivalence

**Covers:** P15 · **Depends on:** SB-O27, SB-O18 · **Target(s):** `skybind`, `skybind_webui`, `skybind_android_device`.

**Allowed primary file scopes:** `internal/webui/bridge`, `cmd/skybind`, `module/webroot/bridge.js`, `module/action.sh`, `tests/webui-bridge`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Implement fixed skybind webui bridge entrypoint carrying base64url-encoded typed request and bounded response. Discover supported embedded APIs by observed capabilities, never by brand alone; preserve request_id/events/errors and ownership rules. Fallback to standalone only after real launch/availability proof. Test bridge exceptions, unavailable manager, version drift and equivalent visual flow.

**Targeted validation / evidence:** CLI/HTTP/embedded contract triples, malformed base64, missing API, old protocol, transport failure, root-manager capability and notification/focus regression tests.

**Mandatory negative gate:** A browser can execute privileged shell, missing bridge is treated as success, or transport changes backend behavior blocks.

**Promotion criterion:** Embedded and standalone views share one feature surface with identical security and UX semantics.

**Devtool deliverable:** `SB-O28.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

### Wave G — Direct-copy WebUI fidelity and full UX parity

#### SB-O29 — Direct-copy frontend shell, tokens and baseline fixture runner

**Covers:** P16 · **Depends on:** SB-G06, SB-O01 · **Target(s):** `skybind_webui`.

**Allowed primary file scopes:** `module/webroot/index.html`, `module/webroot/style.css`, `module/webroot/app.js`, `module/webroot/model.js`, `module/webroot/bridge.js`, `module/webroot/icon.png`, `tests/webui/fixtures`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Copy the checked-in reference WebUI files directly; preserve navigation Home/Mounts/Jobs/Activity/More, desktop sidebar, fixed mobile bar, topbar, badges, design tokens, dark/light mode, 760px breakpoint, motion and safe-area behavior, original local icon and assets. Delete only excluded-feature DOM/state/handlers and adapt backend calls through a tiny adapter; retain untouched reference hashes, source diff and deterministic snapshot fixture server. No framework rewrite or redesign.

**Targeted validation / evidence:** Reference SHA-256 and DOM ID/token audit, static JS checks, 360/390/412/691/759/760/1024px screenshot fixtures, both palette modes, original-vs-copy semantic diff.

**Mandatory negative gate:** Changing nav hierarchy, swapping framework/design tokens, new icon set, orphaned excluded handler, unexplained visual drift or missing golden fixture blocks.

**Promotion criterion:** User-recognizable UI shell is copied rather than reinterpreted and is ready for progressive backend hookup.

**Devtool deliverable:** `SB-O29.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

#### SB-O30 — Home and Mounts exact interaction and wizard parity

**Covers:** P16 · **Depends on:** SB-O29, SB-O08, SB-O10, SB-O13, SB-O23 · **Target(s):** `skybind_webui`, `skybind`.

**Allowed primary file scopes:** `module/webroot/app.js`, `module/webroot/model.js`, `tests/webui/home-mounts`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Preserve Home hero/status, Runtime/Mounts/FUSE/Network four-card order, attention box, two quick actions, mount and activity previews and backend-authority/Refresh panel. Preserve Mounts cards/badges and contextual bottom sheet Start/Stop/Restart/Edit/Activity/Logs/Delete, config rollback and exact Source → Destination → Behavior → Review wizard: remote picker/manual entry/probe, destination suggestion, VFS/resource advanced fields, sticky navigation and proof-bound Apply. Keep focus return, error timing and unsaved-change behavior.

**Targeted validation / evidence:** Golden screenshots for normal/loading/blocked/error cases, wizard step traces and keyboard/focus audit, mocked and real Go API fixtures, stale-proof/duplicate target/password absence cases.

**Mandatory negative gate:** Different wizard step order, different action-sheet semantics, missing fields or deceptive success/errors blocks.

**Promotion criterion:** Home and Mounts visually and functionally match original UI with backed typed operations.

**Devtool deliverable:** `SB-O30.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

#### SB-O31 — Jobs and Activity exact UI/UX parity

**Covers:** P16 · **Depends on:** SB-O30, SB-O20, SB-O21, SB-O07 · **Target(s):** `skybind_webui`, `skybind`.

**Allowed primary file scopes:** `module/webroot/app.js`, `module/webroot/model.js`, `tests/webui/jobs-activity`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Preserve existing job cards/form, enabled state, copy/sync/check type, every/policy controls, preview/confirm, last/next run, run/cancel, progress/status/ETA and error banners. Preserve Activity operation cards, grouping/order, timestamps, structured details, cancel availability and refresh/busy behaviors. Remove only historical out-of-scope controls while keeping the source styling, cards and dialog flow.

**Targeted validation / evidence:** Jobs create/edit/run/cancel/unsafe sync fixture traces, Activity event/cancellation rendering, live refresh and empty/error screenshot matrices, keyboard/screenreader checks.

**Mandatory negative gate:** Reformatting jobs as generic table, losing journal details, false cancelability, stale task display or unconfirmed sync button action blocks.

**Promotion criterion:** Existing Jobs and Activity remain familiar and faithfully represent durable backend state.

**Devtool deliverable:** `SB-O31.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

#### SB-O32 — More, Runtime, Remotes, Doctor, Logs and Settings parity

**Covers:** P16 · **Depends on:** SB-O31, SB-O22, SB-O24, SB-O26 · **Target(s):** `skybind_webui`, `skybind`.

**Allowed primary file scopes:** `module/webroot/app.js`, `module/webroot/model.js`, `tests/webui/secondary`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Retain More cards/navigation; Runtime provenance, immutable status, per-mount/VFS/cache/RC/policy/namespace sections; Remotes chips, browse breadcrumbs, folder/item sheet, endpoint copy/handoff, crypt password status and creation modal; Doctor severity cards, fixes, support ZIP; Logs technical list with severity/source/search, follow/pause, copy/export/clear-view only; Settings grouped cards, appearance, default page, dense mode, reduced motion, refresh and session idle, limits, diagnostics/About. Align settings options with backend without silently removing visible choices.

**Targeted validation / evidence:** Per-screen reference screenshots dark/light and narrow/wide, browse/crypt modal traces, log filtering, support download, settings revision conflict and nonsecret transport tests.

**Mandatory negative gate:** Changing hierarchical navigation, deleting in-scope controls, misleading runtime capabilities, hidden credential fields or unapproved style drift blocks.

**Promotion criterion:** Every More subview, modal, settings control and backend feedback path is preserved.

**Devtool deliverable:** `SB-O32.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

#### SB-O33 — Responsive/accessibility/end-to-end dual-transport UX qualification

**Covers:** P16 · **Depends on:** SB-O32, SB-O28 · **Target(s):** `skybind_webui`, `skybind_android_device`.

**Allowed primary file scopes:** `tests/webui/visual`, `tests/webui/interaction`, `tests/webui/a11y`, `docs/ux`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Run original-vs-recreation visual and interaction parity at 360, 390, 412, 691, 759/760 and 1024px; dark/light, dense/default, reduced motion/enlarged text, portrait/landscape, keyboard open, long paths, offline/session-expired, modal/sheet, empty/loading/failure and stale proof. Verify focus traps/return, escape/device back, live notices, aria-busy, ≥44px targets, keyboard navigation and Android safe-area. Test all retained flows through both standalone and embedded transports; exceptions require exact screenshots, reason and reviewer decision.

**Targeted validation / evidence:** Deterministic reference screenshots and diff policy, real browser scripted traces, a11y scanner plus human review; device WebView screenshots when available; explicit no-unexplained-drift audit.

**Mandatory negative gate:** No golden baseline, visually novel UI, unapproved visual/flow changes, trap regression or claiming embedded parity solely from static tests blocks.

**Promotion criterion:** WebUI preservation is an independently gated acceptance contract, not a theme preference.

**Devtool deliverable:** `SB-O33.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

### Wave H — Integration, hardware qualification and release proofs

#### SB-O34 — Whole-product fault injection, security and recovery matrix

**Covers:** P17 · **Depends on:** SB-G07, SB-G04, SB-G05 · **Target(s):** `skybind`, `skybind_release`.

**Allowed primary file scopes:** `tests/integration`, `tests/security`, `tests/fault`, `scripts/dev/release-audit`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Build cross-subsystem fixtures: corrupt runtime/manifest, PID reuse, state symlink swap, stale proof, race in config, mount/namespace loss, cache pressure, duplicate scheduler claim, RC credential disclosure, nested crypt, interrupted provider action, log/bundle canaries, slow HTTP clients and crash during restart/uninstall. Bind each test to a unique issue/obligation and failed-vs-fixed evidence. Add targeted plus affected-graph retest and regression freeze.

**Targeted validation / evidence:** Independent Go/Python/Node fixture suites, fuzz/sanitizer subsets, race tests, secret canary scan, integrity and source/API/full-UX closure; reproduce injected failures.

**Mandatory negative gate:** Any P00–P17 in-scope feature lacks an evidence owner/test, or any critical safety failure persists blocks.

**Promotion criterion:** Integration and negative safety contracts are complete before device release attempts.

**Devtool deliverable:** `SB-O34.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

#### SB-O35 — Arm64 install, ordinary-app visibility and endurance qualification

**Covers:** P17 · **Depends on:** SB-O34, SB-O19, SB-O33 · **Target(s):** `skybind_android_device`, `skybind_release`.

**Allowed primary file scopes:** `tests/device`, `scripts/dev/device`, `docs/qualification`, `.github/workflows`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Qualify each produced provider ZIP on actual declared supported arm64 devices, record Android fingerprint/API/kernel/SELinux/root manager/version/capabilities plus rclone/FUSE hashes. Test install, boot, Action, mount read/write from a NORMAL Android app, namespace churn, work profile if present, cold/warm reboots, multi-mount/jobs, network/doze/charging/storage/auth/fuse faults, daemon death, WebUI transports, cache, uninstall retention and explicit purge. Use Devtool device manager/ADB operations and shell/push/pull/logcat/screenshot as appropriate. If a real device is absent, mark DEVICE BLOCKED—not PASS.

**Targeted validation / evidence:** Device facts capture, per-scenario immutable receipts, attached logs/screenshots, reproducible APK helper instrumentation only when an actual test-app target exists, targeted cross-provider matrix.

**Mandatory negative gate:** A rooted shell being able to read a mount cannot substitute for ordinary-app access; an emulator/host-only result cannot claim phone/endurance pass; untested managers remain unqualified.

**Promotion criterion:** Supported hardware claims are backed by exact devices, both runtime variants and authentic app read/write observations.

**Devtool deliverable:** `SB-O35.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

#### SB-O36 — Supply-chain audit, reproducible release and final seal implementation

**Covers:** P17 · **Depends on:** SB-O35, SB-O05, SB-O34 · **Target(s):** `skybind_release`, `skybind_runtime_inputs`, `skybind`, `skybind_webui`.

**Allowed primary file scopes:** `scripts/dev/release`, `docs/release`, `.github/workflows`, `tests/seal`. The exact inventory is fixed when packaging the real overlay; undeclared files must not be imported or deleted.

**Implement:** Create final evidence crosswalk binding source commit, exact Devtool run IDs, overlay history, validation reports, package hashes, ELF identities, dependency inventory, UI screenshots/interaction traces, Android device receipts and unresolved-blocker ledger. Reproduce two provider ZIPs and checksum/provenance/SBOM sidecars, sign/attest where policy actually applies (do not impose APK signing on root module ZIP), produce docs for deployment/retained state/limitations/support. Implement project FS1 checker and truthful source-only vs device-release status. Invoke Devtool native final-seal as complementary target audit, not a replacement for Skybind-specific qualification.

**Targeted validation / evidence:** Release manifests, checksum compare, clean rebuild, artifact registry verify, source-state/hash and device receipt provenance; tampered/expired/absent evidence rejection.

**Mandatory negative gate:** Any critical blocker, stale device proof, unverifiable artifact, fake seal claim, unresolved UI parity exception or unsupported manager marked supported blocks.

**Promotion criterion:** Release and final seal are deterministic and evidence-bound, with no false promotion from source-only gates.

**Devtool deliverable:** `SB-O36.devtool-overlay.zip` + target-local validation job(s) + evidence receipt (`overlay SHA-256`, `source commit`, `run_id`, executed test IDs/outcomes, manifest/preflight result, warning counts, scoped changed-file hashes); label `TARGETED_PASS` only after the transaction passes.

## E. Gate overlays (each is a separate applied and executed Devtool artifact)

### SB-G01 — Foundation and static supply-chain milestone

**Dependencies:** SB-O01, SB-O02, SB-O03, SB-O04, SB-O05. **Delivery:** `SB-G01.devtool-overlay.zip` adding `scripts/dev/gates/sb_g01.py`, targeted tests, `.devtool.toml` workflow entries and authoritative `docs/gates/SB-G01.md`. The gate overlay must be committed and validated like any other overlay.

**Gate checks:** Recheck authoritative contract, target graph, private path invariants, signed/pinned input authenticity where applicable, single runtime, NewFuture helper and both provider reproducibility. Verify no excluded paths/features entered new code.

**Assurance ceiling:** SOURCE_BUILD_PASS only; device capability and FUSE usability remain NOT_ATTESTED.

**Required evidence:** per-dependency overlay archive hashes, Devtool apply commits, graph-complete targeted test results, explicit negative-case evidence, zero critical blockers, warning classification, coverage ledger, signed/hashed report where applicable and a machine-readable gate status. A gate can fail, pause or be blocked; it cannot be declared passed because its report file exists. Gate report source must be hashed against the exact code evaluated.

### SB-G02 — Typed authority and transactional configuration milestone

**Dependencies:** SB-G01, SB-O06, SB-O07, SB-O08, SB-O09. **Delivery:** `SB-G02.devtool-overlay.zip` adding `scripts/dev/gates/sb_g02.py`, targeted tests, `.devtool.toml` workflow entries and authoritative `docs/gates/SB-G02.md`. The gate overlay must be committed and validated like any other overlay.

**Gate checks:** Recheck protocol/daemon owner lock, full operation registry, durable journal, proof replay/race/failure, config atomic publish/rollback and CLI parity under malformed/adversarial input.

**Assurance ceiling:** SOURCE_CONTROL_PASS; no real Android mount, daemon boot or device inference.

**Required evidence:** per-dependency overlay archive hashes, Devtool apply commits, graph-complete targeted test results, explicit negative-case evidence, zero critical blockers, warning classification, coverage ledger, signed/hashed report where applicable and a machine-readable gate status. A gate can fail, pause or be blocked; it cannot be declared passed because its report file exists. Gate report source must be hashed against the exact code evaluated.

### SB-G03 — Mount lifecycle, recovery and resource safety milestone

**Dependencies:** SB-G02, SB-O10, SB-O11, SB-O12, SB-O13, SB-O14. **Delivery:** `SB-G03.devtool-overlay.zip` adding `scripts/dev/gates/sb_g03.py`, targeted tests, `.devtool.toml` workflow entries and authoritative `docs/gates/SB-G03.md`. The gate overlay must be committed and validated like any other overlay.

**Gate checks:** Run real Linux helper fixture plus virtual proc/mountinfo/FUSE scenarios, PID reuse, explicit stop stability, policy/VFS/cache symlink/disk-pressure matrix and supervisor fault injection. Require bounded retries and cache ownership.

**Assurance ceiling:** HOST_LIFECYCLE_PASS; Android app visibility remains unqualified.

**Required evidence:** per-dependency overlay archive hashes, Devtool apply commits, graph-complete targeted test results, explicit negative-case evidence, zero critical blockers, warning classification, coverage ledger, signed/hashed report where applicable and a machine-readable gate status. A gate can fail, pause or be blocked; it cannot be declared passed because its report file exists. Gate report source must be hashed against the exact code evaluated.

### SB-G04 — Android namespace/platform source-safety milestone

**Dependencies:** SB-G03, SB-O15, SB-O16, SB-O17, SB-O18, SB-O19. **Delivery:** `SB-G04.devtool-overlay.zip` adding `scripts/dev/gates/sb_g04.py`, targeted tests, `.devtool.toml` workflow entries and authoritative `docs/gates/SB-G04.md`. The gate overlay must be committed and validated like any other overlay.

**Gate checks:** Exercise protected-process scans, multi-user alias truth, safe setns planner, transactional bind ownership/rollback, module shell hooks and conservative uninstall. Require root-manager capability coverage without asserting devices not present.

**Assurance ceiling:** ANDROID_SOURCE_PASS only; separate optional DEVICE_PROVISIONAL evidence, never a device release seal.

**Required evidence:** per-dependency overlay archive hashes, Devtool apply commits, graph-complete targeted test results, explicit negative-case evidence, zero critical blockers, warning classification, coverage ledger, signed/hashed report where applicable and a machine-readable gate status. A gate can fail, pause or be blocked; it cannot be declared passed because its report file exists. Gate report source must be hashed against the exact code evaluated.

### SB-G05 — Jobs, RC, remotes and crypt security milestone

**Dependencies:** SB-G03, SB-O20, SB-O21, SB-O22, SB-O23, SB-O24. **Delivery:** `SB-G05.devtool-overlay.zip` adding `scripts/dev/gates/sb_g05.py`, targeted tests, `.devtool.toml` workflow entries and authoritative `docs/gates/SB-G05.md`. The gate overlay must be committed and validated like any other overlay.

**Gate checks:** Cross-check scheduled due-run at-most-once, destructive sync proofs, cancellation/process owner, loopback RC credential isolation, bounded browse/config secrets, password and crypt wrapper defaults/negative cases.

**Assurance ceiling:** BACKEND_FEATURE_PASS; network/auth/provider behavior remains fixture-qualified until a device/network run.

**Required evidence:** per-dependency overlay archive hashes, Devtool apply commits, graph-complete targeted test results, explicit negative-case evidence, zero critical blockers, warning classification, coverage ledger, signed/hashed report where applicable and a machine-readable gate status. A gate can fail, pause or be blocked; it cannot be declared passed because its report file exists. Gate report source must be hashed against the exact code evaluated.

### SB-G06 — Diagnostics and dual Web transport security milestone

**Dependencies:** SB-G02, SB-G04, SB-G05, SB-O25, SB-O26, SB-O27, SB-O28. **Delivery:** `SB-G06.devtool-overlay.zip` adding `scripts/dev/gates/sb_g06.py`, targeted tests, `.devtool.toml` workflow entries and authoritative `docs/gates/SB-G06.md`. The gate overlay must be committed and validated like any other overlay.

**Gate checks:** Check Doctor and support bundle secret canaries, HTTP bootstrap/session/CSRF/Origin/Host/CSP, embedded bridge request equivalence and fallback truth, source-only transport integration.

**Assurance ceiling:** TRANSPORT_SECURITY_PASS; embedded real-manager claim remains device-pending.

**Required evidence:** per-dependency overlay archive hashes, Devtool apply commits, graph-complete targeted test results, explicit negative-case evidence, zero critical blockers, warning classification, coverage ledger, signed/hashed report where applicable and a machine-readable gate status. A gate can fail, pause or be blocked; it cannot be declared passed because its report file exists. Gate report source must be hashed against the exact code evaluated.

### SB-G07 — Near-exact original WebUI UI/UX preservation milestone

**Dependencies:** SB-G06, SB-O29, SB-O30, SB-O31, SB-O32, SB-O33. **Delivery:** `SB-G07.devtool-overlay.zip` adding `scripts/dev/gates/sb_g07.py`, targeted tests, `.devtool.toml` workflow entries and authoritative `docs/gates/SB-G07.md`. The gate overlay must be committed and validated like any other overlay.

**Gate checks:** Compare immutable original assets and adopted ones, collect screen/state/viewports/both palette screenshots, flow traces, responsive safe areas and a11y results. Review every meaningful diff/exception; audit excluded-only controls are surgically absent.

**Assurance ceiling:** WEBUI_PARITY_PASS only with real reference baseline; if Android embedded screenshots absent, mark its device slice PENDING.

**Required evidence:** per-dependency overlay archive hashes, Devtool apply commits, graph-complete targeted test results, explicit negative-case evidence, zero critical blockers, warning classification, coverage ledger, signed/hashed report where applicable and a machine-readable gate status. A gate can fail, pause or be blocked; it cannot be declared passed because its report file exists. Gate report source must be hashed against the exact code evaluated.

### SB-G08 — Whole-product source/integration and release readiness milestone

**Dependencies:** SB-G01, SB-G02, SB-G03, SB-G04, SB-G05, SB-G06, SB-G07, SB-O34, SB-O35, SB-O36. **Delivery:** `SB-G08.devtool-overlay.zip` adding `scripts/dev/gates/sb_g08.py`, targeted tests, `.devtool.toml` workflow entries and authoritative `docs/gates/SB-G08.md`. The gate overlay must be committed and validated like any other overlay.

**Gate checks:** Run affected then full source/integration/security/reproducibility matrices, verify required real-device receipts when available; compile dependency and unresolved-blocker ledger and cryptographically identify candidate ZIPs.

**Assurance ceiling:** CANDIDATE_READY requires all source gates; DEVICE_RELEASE_READY only with required real-device evidence and no critical blockers.

**Required evidence:** per-dependency overlay archive hashes, Devtool apply commits, graph-complete targeted test results, explicit negative-case evidence, zero critical blockers, warning classification, coverage ledger, signed/hashed report where applicable and a machine-readable gate status. A gate can fail, pause or be blocked; it cannot be declared passed because its report file exists. Gate report source must be hashed against the exact code evaluated.

## F. SB-FS1 — Final whole-product Devtool seal overlay

`SB-FS1.devtool-overlay.zip` installs the Skybind-specific **final-seal verifier, source/feature closure checker and release-candidate evidence policy** under `scripts/dev/seal/`, tests under `tests/seal/`, release workflow entries in `.devtool.toml`, and a report schema with no handwritten `PASS` shortcuts.

**Identity gate:** verify module.prop ID/display name, CLI/daemon binary and socket names, state paths, repo metadata, target IDs, release paths, and WebUI visible labels all conform to the Skybind table. A mismatch blocks the seal; no retroactive alias or migration shim is in scope.

**Prerequisites:** all `SB-G01`…`SB-G08` completed with dependency-qualified receipts; every implementation overlay's final status `TARGETED_PASS`; current source hashes match receipt hashes; no relevant source/config/toolchain change since targeted/gate checks; original WebUI parity approved for the actual shipping code; both provider archives reproducibly hashed; signed release evidence if signing policy requires it; at least one actual supported Android arm64 device and authentic ordinary-app file read/write through Skybind mounted path; installation/bootstrap/namespace recovery/uninstall endurance evidence; all critical findings closed.

**Seal evaluation:**

1. **Immutable source chain:** enumerate 45 planned IDs; verify all required predecessors and gate overlays were applied, committed, validated, and not rolled back; compare current file provenance, artifact inventory, source commit, Devtool history and run IDs.
2. **Full feature matrix:** match every P00–P17 in-scope requirement and every typed operation to backend test(s), UI flow(s) where applicable, negative proof(s) and current evidence; reject unowned/untested features and excluded-feature reintroduction.
3. **Provider packages:** re-run/review both NewFuture/bclone build pipelines, arm64 ELF checks, one-runtime invariant, canonical NewFuture FUSE helper/library, hashes, deterministic ZIPs and SBOM/dependency inventory.
4. **Security/lifecycle:** zero critical vulnerabilities across config/proof, PID/FUSE/process ownership, namespace protection, root-manager hooks, cache and uninstall, job destructive sync, secret handling, transport and support export.
5. **WebUI almost-identical parity:** source-origin proof for all copied assets, complete Home/Mounts/Jobs/Activity/More and secondary screens, before/after screenshot matrix, interaction traces, a11y/mobile/device behavior and reviewer-approved surgical deviations only.
6. **Real Android qualification:** exact APK helper (if any) and device module install facts, boot/daemon/run/stop, app read/write, alias truth vs configured target, namespace churn, multi-user exercised-or-not labels, outage/screen-off/reboot, provider variants and manager-specific claims. Device receipts must include build fingerprint and exact software hashes.
7. **Host and runtime matrix:** distinguish source tests from Linux fixtures, native Termux/chroot builds, app root manager, physical device and remote-network proof. No inference from one tier to another.
8. **Operational release:** safe install/uninstall/purge, docs for credentials/cache/state, support bundle redaction, checksums/SBOM/known limitations, machine-readable unresolved obligation ledger and release artifacts verified through Devtool registry.
9. **Devtool authoritative status:** run `devtool final-seal --target skybind --strict --json` and applicable other configured target audits, then the Skybind-specific FS1 workflow. Archive both distinct reports and never merge their statuses as if identical.

**Outputs:** `NX_FS1_FINAL_ATTESTATION.json`, `NX_FS1_FINAL_SEAL_REPORT.md`, `NX_FS1_FEATURE_COVERAGE.json`, `NX_FS1_DEVICE_MATRIX.json`, `NX_FS1_ARTIFACT_PROVENANCE.json`, release ZIP(s) with SHA-256/provenance/SBOM, Devtool run IDs + phase reports, and a machine reason for any `BLOCKED` determination. Target and source names are illustrative until the seal overlay implements them.

**Authoritative rule:** `SEALED` is impossible without authentic required device evidence. If physical device testing is unavailable, generate an honest `SOURCE_CANDIDATE_READY / DEVICE_BLOCKED` report, **not** a release seal.

## G. Concrete targeted-validation matrix and progressive gates

| Changed feature | Minimum overlay tests | Milestone rechecks | Device/release addition |
|---|---|---|---|
| Runtime provider/integrity | ELF/provenance/hash/unit, deterministic 2-build comparison, corrupt archive | G01,G08,FS1 | Boot both arm64 providers and verify helper bytes |
| Go state, protocol, journal/proofs | path safety, socket, schema/fuzz, crash journal, revision/proof replay | G02,G08,FS1 | Daemon death/boot reattach |
| Mount lifecycle/supervisor | PID/start-time/mountinfo, false ownership, stop/reconcile race, retry budgets | G03,G08,FS1 | Real FUSE, storage churn, network/auth/doze |
| Policy/VFS/cache | exact profile constants, conservative unknown network, active-cache deletion denial, symlink swap | G03,G08,FS1 | Cache pressure/charging/network switching |
| Android namespace mutation | alias/path/user facts, protected process denies, bind failure rollback, cleanup ownership | G04,G08,FS1 | Ordinary app exact-path read/write and namespace churn |
| Root manager/platform/uninstall | capability fixture matrix, shell hooks, package corruption, preserve/purge negative | G04,G08,FS1 | Qualified manager/version device install/reboot/uninstall |
| Scheduled jobs/RC | due-run at-most-once, policy guard, destructive sync proof, cancel, auth/loopback isolation | G05,G08,FS1 | Live copy/sync/check and telemetry |
| Provider/crypt/credentials | bounded remote browse, secret canary, nested/self crypt denial, config rollback | G05,G08,FS1 | Real remote access and encrypted file round-trip |
| Doctor/logs/support | PASS/WARN/FAIL truth, rotated bounds, sanitized archive, secret scan | G06,G08,FS1 | Live logs/support export and content inspection |
| Web transports | HTTP token/cookie/CSRF/Host/Origin, embedded bridge equivalence, XSS | G06,G07,G08,FS1 | Real standalone browser + root manager WebUI |
| WebUI direct reuse | original file hashes, DOM/action map, screenshots, interaction parity and a11y | G07,G08,FS1 | WebView/mobile gesture/keyboard/safe area |
| End-to-end/release | fault suite, evidence graph, provenance/SBOM, source coverage, critical ledger | G08,FS1 | Physical Android endurance and one normal-app read/write |

**Risk-sensitive validation intensity:** overlays touching `internal/namespace`, mount ownership, uninstall or crypt must add adversarial negatives before being applied; device-dependent effects require sandbox fixtures AND separately recorded device experiments. The release workflow cannot replace targeted security checks with a generic success smoke.

## H. Baseline WebUI preservation contract (applies to O01 and O29–O33 and G07/FS1)

**Files to import directly:** `module/webroot/index.html`, `style.css`, `app.js`, `model.js`, `bridge.js`, `icon.png`, `config.json`, `platform.json`; source authority is the inspected, declared original snapshot. Preserve vanilla HTML/CSS/ES modules, layout, design tokens, five destinations, four-stage Mount wizard, action sheets, modals, status and error handling, typography, icons, responsiveness, accessibility, mobile safe areas, back/focus behavior and both transport UX. No React/Vue/Tailwind substitute or cosmetic reinterpretation.

**Reference SHA-256 manifest (from existing roadmap):**

| Asset | SHA-256 in inspected source snapshot |
|---|---|
| `index.html` | `aa0c2421094e091e6ac0230bdc8673b8b276e1a7b304dd516ffb0f75b0e2d9b7` |
| `style.css` | `811a76708fd530d8d547ee91d3cda5ed82354ea97ab7b96be970b067d870cfcb` |
| `app.js` | `14febfe3643d6e0e21fdf0a40ec2c3824088af5a1bacb1998efb090d835d2d48` |
| `model.js` | `a78b6f8037e949717f440b1bee984507068bd1ff6c7a6f3b9316a98a9247ff6b` |
| `bridge.js` | `8413d193335b7589b0bc9982f29c92beccc3aefbd474328973e36c6a24497797` |
| `icon.png` | `9f7234a76f01f665611649dd5bb971a141389f192f4ec31f7652e8c73eef1614` |
| `config.json` | `e7060f44e35a5bfebfd9b4a476046777965e3ca92ff2a884fc4487ec67dbd165` |
| `platform.json` | `1ea2dff80636a7cfb2eb074d108df387c5645e13709449ad0b9d616a85d9062b` |

These hashes identify the original files for comparison and auditing, **not** hashes that the altered in-scope frontend must retain after approved exclusions and necessary wiring changes. Keep the untouched originals as read-only baseline evidence. Frontend code must not be blindly imported if it calls out-of-scope backend operations.

**Required parity screenshots/states:** 360/390/412px phones, 691px narrow portrait, 759/760px breakpoint, 1024px desktop; dark/light, default/dense, reduced motion/enlarged fonts, portrait/landscape, software keyboard, long paths; idle/empty/loading/blocked/success/failure/offline/expired/stale-proof; each dialog and bottom sheet. Compare identical data/DPR/font/motion context; inspect perceptual diffs and interaction/focus traces. A pixel score alone does not establish UX parity; a source diff alone does not establish visual parity.

**Feature-to-UI screens:** Home status/4-card grid/quick actions; Mounts cards/actions and Source→Destination→Behavior→Review wizard; Jobs and Activity native cards; More and Runtime/Remotes/Doctor/Logs/Settings subviews; crypt modal, typed previews and confirmations, refresh/polling/cancel behavior. Removing a sole-purpose excluded control is a justified difference; wholesale reflow or relabeling is not.

**UI review record per permitted deviation:** baseline screen/DOM/state, changed lines, why minimal adapter or unchanged UI was insufficient, screenshots/interaction traces, security/accessibility impact, explicit reviewer approval and overlay ID. Unreviewed UI drift blocks SB-G07.

## I. Planned Devtool project wiring sketch (not yet applied)

```toml
[project]
runner = "command"
platform = "cli"

[workspace]
default_target = "skybind"

[workspace.groups]
source = ["skybind", "skybind_webui", "skybind_runtime_inputs"]
release = ["@source", "skybind_android_device", "skybind_release"]

[workspace.scheduler]
parallel = true
max_parallel_nodes = 3
max_gradle_nodes = 1

[targets.skybind]
runner = "command"
platform = "cli"
root = "."
inputs = ["go.mod", "cmd/**", "internal/**", "module/**", "tests/**"]

[targets.skybind.jobs.sb_o08_config_go]
runner = "command"
command = ["go", "test", "-count=1", "./internal/mounts", "./internal/previewproof"]
inputs = ["go.mod", "internal/mounts/**", "internal/previewproof/**"]
metadata = { read_only = true }

[targets.skybind.jobs.sb_o08_config_negative]
runner = "command"
command = ["python3", "-m", "pytest", "-q", "tests/config/test_registry_negative.py"]
inputs = ["tests/config/**", "internal/mounts/**"]
metadata = { read_only = true }

[targets.skybind.workflows]
sb_o08_targeted = [
  { id = "config-go", ref = "job:sb_o08_config_go", depends_on = [] },
  { id = "config-negative", ref = "job:sb_o08_config_negative", depends_on = ["config-go"] }
]

[targets.skybind_webui]
runner = "command"
platform = "web"
root = "."
inputs = ["module/webroot/**", "tests/webui/**"]

[targets.skybind_runtime_inputs]
runner = "command"
platform = "shared"
root = "."
inputs = ["scripts/dev/runtime/**", "module/system/**"]

[targets.skybind_android_device]
runner = "command"
platform = "android"
root = "."
inputs = ["module/**", "tests/device/**", "scripts/dev/device/**"]

[targets.skybind_release]
runner = "command"
platform = "shared"
root = "."
inputs = ["scripts/dev/release/**", "docs/release/**", "tests/seal/**"]
```

**This is a configuration design sketch, not a complete running `.devtool.toml`:** the command runner requires project-specific native actions/workflows; Android shell/device jobs must be explicitly defined and dry-run-planned; and any test ID in an overlay manifest must point to a real registered test specification, not merely a local job name. Reconcile exact parser constraints with the uploaded Devtool version via `devtool config doctor`, `jobs`, `workflows`, `plan`, and `preflight` before shipping O02.

## J. Execution discipline and handoff format

For each planned `SB-Oxx` or `SB-Gxx`:

1. **Discover:** verify last admitted gate/overlay, Git commit and file hashes, active Devtool transaction/session, target availability, toolchains and device only if the operation requires one.
2. **Scope:** enumerate features, exact source changes, prerequisites, expected public API/UI changes, forbidden/excluded features, and declared read/write paths. Freeze at least one positive, one failure and one security/race counterexample.
3. **Build the overlay:** write only scoped repo-relative files and tests; generate inventory hashes, source-hash guards and JSON-v1 hooks. Register real targeted tests and workflows before referring to them.
4. **Dry-run/inspect:** use `overlay check --json`, `inspect-artifact`, `validate-overlay`, config `plan` and `preflight`. Resolve an inventory or source conflict before apply. Never bypass SHA-256 for speed.
5. **Apply with validation:** atomic Devtool transaction, selected environment, appropriate per-overlay tests, explicit warning/failure policy, commit only after checks succeed. Use durable sequential validation for expensive matrices.
6. **Failure/recovery:** inspect run ID/logs/validate status+plan+events. Target failure -> fix and retry affected graph; resource/environment interruption -> safe retry/recover after correction; identity/source mismatch -> stop and reviewed rebase; explicit rollback only via Devtool.
7. **Evidence:** store actual test counts, selected phases, warning counts split by target/infra, run ID, source commit, produced-artifact/hash IDs, skipped device slices and their reason; show no seal/pass status unless the authoritative check returned one.
8. **Gate promotion:** apply the gate overlay, run graph-complete regression closure, mark exact source-level assurance only; seal source and device separately. Record follow-up obligations as BLOCKED, never silently deferred PASS.
9. **Handoff:** concise next overlay, exact prerequisites/evidence, known blockers, changed scopes, unqualified Android claims, replay commands with sanitized arguments, and rollback/recovery point.

**Do not proceed past a failed required gate.** A source-only pass can enable the next source overlay, but cannot approve a device release. A Devtool Android notification/HUD status is an observer of the authoritative session, not an independent gate verdict.

## L. All 57 typed API operations — explicit overlay ownership

The prior roadmap named **57 typed operations**. This table imports that exact catalog and assigns every operation to one implementation overlay and the corresponding original UI consumers. An implementation overlay may expose only its genuinely implemented operations as available; a future-operation stub must report unsupported capability, not fake success. P09/UI settings declarations must align with visible settings exactly. Product security remains enforced by the backend regardless of frontend source-copy fidelity.

| Typed operation | Class | Implemented by | original WebUI consumer |
|---|---|---|---|
| `runtime.status` | query | SB-O04 | Runtime, Home |
| `provider.status` | query | SB-O23 | Remotes, Mount wizard |
| `provider.remotes` | query | SB-O23 | Remotes, Mount wizard |
| `provider.browse` | query | SB-O23 | Remotes, Mount wizard |
| `provider.crypt.password.status` | query | SB-O24 | Remotes/crypt modal, Settings |
| `provider.crypt.password.set` | run | SB-O24 | Remotes/crypt modal, Settings |
| `provider.crypt.preview` | preview | SB-O24 | Remotes/crypt modal, Settings |
| `provider.crypt.create` | run | SB-O24 | Remotes/crypt modal, Settings |
| `provider.crypt.recovery.status` | query | SB-O24 | Remotes/crypt modal, Settings |
| `config.snapshot` | query | SB-O08 | Mounts, wizard, rollback |
| `config.validate` | query | SB-O08 | Mounts, wizard, rollback |
| `config.preview` | preview | SB-O08 | Mounts, wizard, rollback |
| `config.apply` | run | SB-O08 | Mounts, wizard, rollback |
| `config.previous` | query | SB-O08 | Mounts, wizard, rollback |
| `config.rollback.preview` | preview | SB-O08 | Mounts, wizard, rollback |
| `config.rollback` | run | SB-O08 | Mounts, wizard, rollback |
| `mount.list` | query | SB-O10 | Mounts, Home, Runtime |
| `mount.status` | query | SB-O10 | Mounts, Home, Runtime |
| `mount.health` | query | SB-O11 | Mounts, Home, Runtime |
| `mount.start.preview` | preview | SB-O10 | Mounts, Home, Runtime |
| `mount.start` | run | SB-O10 | Mounts, Home, Runtime |
| `mount.stop` | run | SB-O10 | Mounts, Home, Runtime |
| `mount.restart` | run | SB-O10 | Mounts, Home, Runtime |
| `mount.reconcile` | reconcile | SB-O10 | Mounts, Home, Runtime |
| `policy.status` | query | SB-O13 | Runtime, Mount wizard |
| `vfs.profiles` | query | SB-O13 | Runtime, Mount wizard |
| `cache.status` | query | SB-O14 | Runtime, Mount wizard |
| `cache.prune.preview` | preview | SB-O14 | Runtime, Mount wizard |
| `cache.prune` | run | SB-O14 | Runtime, Mount wizard |
| `cache.clear.preview` | preview | SB-O14 | Runtime, Mount wizard |
| `cache.clear` | run | SB-O14 | Runtime, Mount wizard |
| `cache.forget.preview` | preview | SB-O14 | Runtime, Mount wizard |
| `cache.forget` | run | SB-O14 | Runtime, Mount wizard |
| `namespace.inspect` | query | SB-O15 | Runtime, Mounts, Doctor |
| `namespace.preview` | preview | SB-O16 | Runtime, Mounts, Doctor |
| `namespace.apply` | run | SB-O16 | Runtime, Mounts, Doctor |
| `namespace.rollback.preview` | preview | SB-O17 | Runtime, Mounts, Doctor |
| `namespace.rollback` | run | SB-O17 | Runtime, Mounts, Doctor |
| `namespace.reconcile` | reconcile | SB-O17 | Runtime, Mounts, Doctor |
| `jobs.snapshot` | query | SB-O20 | Jobs, Activity |
| `jobs.preview` | preview | SB-O20 | Jobs, Activity |
| `jobs.apply` | run | SB-O20 | Jobs, Activity |
| `jobs.status` | query | SB-O20 | Jobs, Activity |
| `job.run.preview` | preview | SB-O21 | Jobs, Activity |
| `job.run` | run | SB-O21 | Jobs, Activity |
| `rc.metrics` | query | SB-O22 | Runtime, Home |
| `operation.status` | query | SB-O07 | Activity |
| `operation.list` | query | SB-O07 | Activity |
| `operation.cancel` | cancel | SB-O07 | Activity |
| `doctor.report` | query | SB-O25 | Doctor, Logs |
| `doctor.bundle` | run | SB-O26 | Doctor, Logs |
| `doctor.bundle.read` | query | SB-O26 | Doctor, Logs |
| `diagnostics.logs` | query | SB-O25 | Doctor, Logs |
| `platform.status` | query | SB-O18 | Runtime, Home |
| `ui.settings` | query | SB-O32 | Settings |
| `ui.settings.preview` | preview | SB-O32 | Settings |
| `ui.settings.apply` | run | SB-O32 | Settings |

**Mandatory machine check:** generate this table from the canonical operation schema and compare (1) the source snapshot catalog, (2) backend operation registration, (3) CLI capability list, (4) direct WebUI requiredOperations, and (5) tests in the responsible overlay. Changes require versioning, specific gate replay and G07 UI parity review; no hidden operation, extra arbitrary command operation or undocumented deletion is permitted.

## M. Gate promise ledger, exported obligations and fixed-point audit

Each `SB-Oxx` overlay must carry a source/feature **promise ledger** and targeted evidence, not just a generic unit test. Each `SB-Gxx` gate overlay must own three independent deliverables:

- `NX_Gxx_PROMISE_LEDGER.json`: one row per claimed feature/state/security invariant; each row has canonical source contract, owning overlay/source path, exact targeted test(s), positive and negative evidence run IDs, status and disposition.
- `NX_Gxx_EXPORTED_OBLIGATIONS_TO_NEXT.json`: unsatisfied downstream or device-only requirements with concrete target gate/overlay and blocking status. Exporting an obligation does **not** make it pass.
- `NX_Gxx_GATE_REPORT.md` plus machine-readable attestation: validated dependency-graph inputs, source commit and file hashes, effective Devtool validation plan, executed test/negative counts, warnings split target/infra, first failure, comparison with prior gate/overlay, and whether a fresh-process rerun reproduced the result.

Gate overlays are **gate-only**: they can add gate scripts, fixture-based gate tests, workflow declarations, reports and registries, but cannot quietly patch the feature implementation under inspection. If a gate exposes a product defect, build a separately identified remediation overlay with an explicit dependency and replay the targeted gate; never alter product logic inside a seal/gate report and call it a pass.

For each gate, require a **fresh-process fixed-point audit** after implementation overlays: rerun the defined source tests from a clean tool session on the same commit; invalidate stale results if any input/hash/task definition changed; recalculate the complete obligation ledger and ensure identical qualified results. `SB-G08` must include all retained source obligations and exported device obligations from `SB-G01`–`SB-G07`, not merely their top-level PASS names.

**Evidence closure invariant:** each row must be one of `satisfied`, `failed`, `device_unverified`, `excluded_by_scope`, or `not_yet_implemented` with a precise owning gate. No blanket family closure, no evidence that only points to another unchecked report, no `PASS` for a skipped mandatory test and no historical migration artifact accepted as current-product proof. `SB-FS1` may seal only when every required row is `satisfied` or legitimately `excluded_by_scope`; the latter must cite the user's explicit exclusions and have no remaining reachable frontend control/API path.

## N. Exact canonical state ownership / testing traceability

| Resource/state | First implementing overlay | Failure/recovery owning overlay | Gate |
|---|---|---|---|
| Installed `system/bin/rclone`, FUSE helper, hash/provenance | SB-O04, SB-O05 | SB-O04/SB-O05, SB-O36 | G01,FS1 |
| `/data/adb/skybind` private directory structure | SB-O03 | SB-O03, SB-O19 | G01,G04 |
| `config/rclone/rclone.conf` and remote types | SB-O23, SB-O24 | SB-O23/SB-O24 | G05 |
| `config/registry-v2.json`, previous known good | SB-O08 | SB-O07/SB-O08 | G02 |
| Desired mount and observed PID/start/mountinfo | SB-O10 | SB-O12 | G03 |
| Health/retry budgets and readiness blockers | SB-O11 | SB-O12 | G03 |
| App namespace visibility and owned-bind journal | SB-O15, SB-O16 | SB-O17 | G04 |
| Per-mount VFS cache pressure and protected contents | SB-O13 | SB-O14 | G03 |
| Job registry, next/last and at-most-once claim | SB-O20 | SB-O21 | G05 |
| Operation journal, events, cancellation | SB-O07 | SB-O07 | G02 |
| Ephemeral RC auth and isolated telemetry | SB-O22 | SB-O22 | G05 |
| Ephemeral Web session and bootstrap authority | SB-O27 | SB-O28 | G06 |
| Revisioned UI preferences | SB-O32 | SB-O32 | G07 |
| Logs and owned redacted support archives | SB-O25 | SB-O26 | G06 |
| Root-manager/platform readiness, uninstall choice | SB-O18 | SB-O19 | G04 |
| Release candidate hashes, device receipts, closure ledger | SB-O36 | SB-G08, SB-FS1 | G08,FS1 |

## K. Final traceability and explicit exclusions

The overlay index JSON (`SKYBIND_DEVTOOL_OVERLAY_INDEX.json`) is a planned machine-readable control ledger: each implementation overlay maps to original P00–P17 phases, dependency IDs, targets, source scopes, positive and negative validations, and the promotion criterion. It is **not** a fabricated Devtool execution report. Each listed ID starts at status `PLANNED`.

**Excluded everywhere:** installed-product runtime hot swapping/provider selection/remote runtime downloads; migration or historical campaign artifacts, old state conversion, outdated compatibility shims and obsolete UX controls serving excluded flows. **Retained:** build-time provider choice; runtime integrity checking (read-only); desired/observed-state reconciliation; transactional rollback/recovery; Devtool validation recovery; durable operation journal; normal upgrades/reinstalls where they don't perform migrations; original frontend appearance and interaction design.

**Whole-product definition of done:** all 45 overlays have genuine, verified delivery records; targeted and milestone closure is current at the release commit; feature/API/UI matrix is 100% assigned and executed; no unresolved security blocker; original WebUI remains practically identical; physical device and ordinary-app filesystem evidence qualify supported Android claims; both immutable provider builds are reproducible; FS1 returns `SEALED` only with authentic evidence. In every other case, the result is precisely labeled source-ready, provisional or blocked.
