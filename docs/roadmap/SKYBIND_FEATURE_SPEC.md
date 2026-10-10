# Skybind — Greenfield Feature Specification

**Naming note:** this specification describes the new **Skybind** product. The named original source snapshot is retained exclusively as historical technical reference, not as a current product identity. The installed upstream binary remains named `rclone`; no migration is intended.

**Reference examined:** recent full-source snapshot `rclone-nexus-20261009-172434-329657.tar.gz`, with the Repair 14 and Repair 15 source overlays applied, plus the current architecture, feature, security, release, frontend, and test contracts. The uploaded Repair 15 archive alone is only a small patch; it is not a complete repository. This plan covers the intended feature-complete Android product, not an assertion that every feature currently works on every device.

**Goal:** Recreate Skybind as a non-invasive, arm64 Android root module with one **statically packaged** rclone-family executable; one separately packaged NewFuture-derived FUSE helper; a root-owned native Go control plane; secure configuration, mount lifecycle, recovery, jobs, Android visibility inspection, crypt remote management, diagnostics, and the **existing WebUI carried forward with near-identical UI and UX**. Rebuild native internals cleanly; **directly reuse the original in-scope frontend**, rather than designing a new interface.

## 1. System architecture and invariants

```text
  source acquisition/build                    Android root-module installation
  NewFuture rclone OR bclone                  /data/adb/modules/skybind/
             |                                            |
   official NewFuture FUSE helper                     system/bin/skybind
             |                                       system/bin/rclone
  provenance + integrity manifest             system/vendor/bin/fusermount3
             +-------------------- package ZIP -----------+
                                                          |
   module hooks -> skybind/skybindd (Go) <- Unix socket -> CLI/bridge/HTTP WebUI
                         |
           typed allow-listed operation registry
                         |
         +---------------+---------------+
         |               |               |
  config/mounts      jobs/RC/cache   namespaces/platform
         |               |               |
         +--------- journal/health/diagnostics -----+
                         |
      /data/adb/skybind/ [persistent, root-private]
```

**Unbreakable properties.** Exactly one `system/bin/rclone` is installed per module. Its content may be NewFuture rclone or an Android/arm64 bclone build, selected while assembling the ZIP. The required `system/vendor/bin/fusermount3` and accompanying `libfuse*.so*` when dynamically distributed come from the official NewFuture arm64 artifact; the reviewed v1.75.0 static-helper layout has no standalone libfuse shared library regardless of the selected runtime. Installed executable selection must not be redirected by `PATH`, arbitrary environment variables, an unrelated executable, or browser input. The canonical managed rclone config is `/data/adb/skybind/config/rclone/rclone.conf`. State lives outside the replaceable module directory. Skybind never evaluates mount configurations as shell code, never offers arbitrary command-line arguments through the protocol, and never assumes a root-shell FUSE mount is available to Android applications.

**Primary boundaries.** Packaging builds the module; `internal/runtimeauth` resolves and verifies its executable; `skybind` exposes human commands and protocol clients; `skybindd` owns the Unix-socket server, scheduler and supervisor; `internal/control` contains all typed operations; the state packages perform mutations; the namespace package alone owns setns/bind logic; the WebUI transports make requests but contain no privileged business logic.

**Non-negotiable WebUI preservation rule.** The WebUI is a **port/copy**, not a conceptual recreation or redesign. Preserve the source UI's layout, styling, navigation, wording, iconography, responsive behavior, forms, modal flow, animation/motion preferences, accessibility, state messaging and user journeys. Treat the existing frontend files as the initial implementation, not merely as inspiration. Make only narrowly justified changes for backend wiring, verified fixes, accessibility/security improvements and removing expressly excluded functionality. Require documented before/after parity evidence. See **P16** and **Section 7**.

**Delivery rule for every stage.** An implementation is complete only with source code, strictly typed inputs/outputs, negative/security tests, integration tests, operational documentation, reproducible build evidence, and a demonstration that its state survives daemon restart where required.

## 2. Recommended repository layout

```text
cmd/skybind/                Go CLI, daemon entry point and fixed compatibility commands
internal/paths/           canonical filesystem locations and private-state initialization
internal/buildinfo/       product/version/protocol constants
internal/protocol/        bounded versioned request/response/event envelopes
internal/control/         fixed operation registry, validation, cancellation/proofs
internal/daemon/          locked socket daemon, client, scheduler, recovery loops
internal/runtimeauth/     sole bundled runtime + provenance resolver
internal/provider/        managed rclone config, credential-free remote browse/crypt
internal/mounts/          typed mount model, registry, desired state, ownership, lifecycle
internal/readiness/       boot, runtime, FUSE, storage, network, reachability graph
internal/supervisor/      health state machine, restart budgets and reconciliation
internal/namespace/       /proc topology, visibility classification, transactional binds
internal/policy/          network/charging/battery/free-space constraints
internal/vfs/             VFS profiles and resource recommendations
internal/cache/           owned-cache metrics, pruning and guarded cleanup
internal/jobs/            revisioned scheduled jobs and execution state
internal/rc/              per-mount authenticated loopback RC metrics
internal/journal/         durable operation records and interrupted-run recovery
internal/previewproof/    short-lived one-use proof issuer/consumer
internal/diagnostics/    bounded structured logs and redaction
internal/doctor/         health checks and sanitized support archives
internal/integrity/      package hash, mode and manifest verification
internal/rootmgr/        capability-based root-framework detection
internal/platformstate/  clean-install, state verification and platform readiness
internal/platformlifecycle/ uninstall cleanup and one-shot purge authority
internal/websettings/    revisioned backend-owned UI preferences
internal/webui/           authenticated localhost server and embedded bridge
module/webroot/          DIRECTLY REUSED WebUI HTML/CSS/JS/icon and local assets
module/                  Android module hooks, wrappers, webroot and metadata
scripts/dev/             arm64 builds, provider acquisition, packaging and gates
tests/                   Python integration, fixture/device and contract tests
.devtool.toml             first-class target-specific orchestration
.github/workflows/        pinned source/build CI, static/package checks
```

All directories above are feature ownership boundaries, not mandates to duplicate an old file line for line. Use narrowly scoped packages with dependency injection for testability; keep control handlers thin and domain logic in domain packages.

## 3. Build phases, in dependency order

### P00 — Specification, exact semantics and threat model

Create a single current-product contract defining file layout, API schema, allowed operations, mount/job configuration fields, proof semantics, lifecycle state machine, Android scope of visibility, root ownership, supported arm64 ABI and exact release criteria. Define adversarial scenarios up front: stale revision, concurrent action, PID reuse, symlink swap, forged ownership marker, changed mount signature, interrupted config publication, RC credential leak, secret in a support bundle, and unexpected app namespace. Produce a traceability table mapping each user feature to code package, CLI command, UI view, and tests. **Freeze the current frontend assets and capture UI/UX screenshots, interaction traces and behavior baselines before backend reconstruction begins; record intentional exclusions separately.**

**Acceptance:** All subsequent phases depend on this contract; source-only tests never count as hardware evidence.

### P01 — Native project skeleton, environment and root-private paths

Initialize Go module, `skybind` executable and version/build metadata. Implement `paths.Paths`, explicit environment overrides strictly for harness tests, and `EnsureState()` with root-private state (`0700` directories, `0600` sensitive files), symlink/path/ownership checks and atomic-write helpers. Define `/data/adb/modules/skybind`, `/data/adb/skybind`, `run/skybindd.sock`, run locks, logs, config registry, health, operations, desired, cache, jobs, namespace, policy, RC, webui and support folders. Add test harnesses for Linux/Termux and Android arm64 cross-build.

**Acceptance:** Same tests work in an unprivileged temporary sandbox without allowing that exception on a privileged device; unsafe existing paths fail closed.

### P02 — Static runtime packaging and supply chain

Implement two build input paths: **NewFuture rclone** downloaded from the official arm64 module artifact and **bclone** built for Android/arm64 from a resolved, immutable source commit using an Android NDK toolchain. Build-time selection may support an explicitly verified offline/prebuilt rclone as an advanced operator input. Regardless of runtime choice, download/extract `fusermount3` and any necessary shared libraries from the **official NewFuture arm64 module** (the reviewed v1.75.0 variant links libfuse statically and ships no `libfuse*.so`); permit no second runtime binary. Verify ELF target ABI, executable status, archive traversal/symlinks, hashes, download authenticity and source provenance. Pin and record commit/tag/toolchain/version; write `runtime.provenance.json` with runtime and helper identities and SHA-256s, plus an integrity manifest covering all shipped bytes, web assets and metadata. Assemble a deterministic ZIP with normalized file order, timestamps, permissions and checksum.

Implement one resolver: bundled `<module>/system/bin/rclone`, bundled `<module>/system/vendor/bin/fusermount3`, and managed config. Check regular files, executable bits, package provenance and hash identity. Runtime view/CLI supports status, executable and config inspection, including `--require-operational`; no executable-selection mutations at runtime.

**Acceptance:** Both NewFuture and bclone packages contain exactly one runtime and the same canonical helper authority; two clean builds from pinned inputs are byte-for-byte identical; altered runtime/helper/provenance blocks operational status; no PATH/env substitution succeeds.

### P03 — Typed protocol and daemon authority

Define `schema_version`, `request_id`, client min/max protocol, operation `{name,class,args}`, response/result or stable machine error, capabilities and event envelopes. Support classes `query`, `preview`, `run`, `cancel`, `reconcile`; strict unknown-field rejection; bounded message sizes (reference defaults: requests/responses 1 MiB, events 256 KiB, strings 64 KiB); bounded streams; recursive redaction; machine-stable error codes, categories, stages and retryability. Add a single operation registry with descriptors and explicit cancellability. Never accept shell, filesystem, arbitrary command, generic RC endpoint or arbitrary argv operations.

`skybindd` must hold a single-instance lock, serve a root-owned local Unix domain socket, negotiate protocol compatibility and shut down cleanly. `skybind` acts as both native CLI and machine client, with protocol JSON/NDJSON streaming, `version`, `capabilities`, `rpc`, and `daemon`. Permit a strictly equivalent local-handler fallback where intended without broadening authorization. Put backend mutations and reconciliation in a durable journal **before** performing them; persist events, progress, owner PID/start identity, success/failure/cancellation; detect abandoned operations as `INTERRUPTED`. Only cancellation-safe operations receive cancel tokens; non-cancellable transactions must not be interrupted mid-commit.

**Acceptance:** Daemon and local entry produce the same typed outcome; unknown operations/classes, oversized/unparseable JSON, stale clients and response flooding fail safely; multiple daemon attempts cannot both own socket; journal survives crash and UI restart.

### P04 — Revisioned mount configuration and safe publication

Create the authoritative `registry-v2.json` and `previous-v2.json` model. Each mount includes `name`, `enabled`, `remote`, `mountpoint`, VFS cache mode/size/age, directory cache time, poll interval, `allow_other`, `read_only`, log level, remote/network requirements, network mode, charging-only, min battery, min cache free space, boot/network settle, VFS profile and cache high/low water marks. Validate names, remote endpoint and options, units/durations, path normalization and absolute target, duplicate/nested targets, dangerous paths and overlap with Skybind private state. Preserve optional *root-local, trusted* `args_file` information server-side but expose at most `has_args_file` publicly; reject browser-supplied argument files and arbitrary flags.

Implement `config.snapshot`, `validate`, `preview`, `apply`, `previous`, `rollback.preview`, and `rollback`. Publication protocol: load revision -> materialize candidate -> normalize -> validate -> compute canonical digest and full diff -> issue one-use expiring proof -> consume proof and re-check revision/digest under lock -> atomically write/fsync/rename registry -> update previous-known-good -> calculate lifecycle actions only for affected mounts. A rollback publishes a **new** revision, not an old revision number. Preview diff includes creates/deletes/edits and lifecycle, cache, policy and namespace consequences. Policy-only edits must not restart an otherwise healthy mount; VFS changes can require restart.

**Acceptance:** Stale/replayed/mismatched proof fails; interrupted publication leaves either a coherent old or new registry; no cross-mount modifications; secrets/private paths absent from the public snapshot.

### P05 — Process-owned mount lifecycle and desired state

Implement mount `list/status/health`, start preview/start, stop, restart and reconcile. For each mount store process PID **and Linux `/proc/<pid>/stat` start time**, process group as appropriate, resolved executable identity, mountpoint, lifecycle log, per-mount cache and last failure. Hold a per-mount interprocess file lock; recheck desired/current/observed state after lock acquisition. Launch exact bundled rclone with explicit `--config`, VFS flags, FUSE helper environment and authenticated per-mount loopback RC, never shell-interpolated strings. Parse mountinfo and process identity separately; do not report `RUNNING` merely because PID exists or the path is mounted.

Persistent desired override `running/stopped` must be distinct from observed state and must survive daemon reboot so explicit stop is respected. Implement graceful TERM -> bounded wait -> repeated identity check -> last-resort KILL; detach only an exact, proven Skybind-owned FUSE mount and release owned namespace binds first. Failed starts return actionable error category, stage and bounded/redacted startup-log tail. One mount failure never blocks others. Reconciliation rechecks desired state under lock, plans affected mounts only, and preserves independent failure domains.

**Acceptance:** PID reuse and coincidentally occupied mountpoint never signal/unmount a stranger; simultaneous stop/reconcile does not reanimate explicitly stopped mount; multiple mounts remain independent.

### P06 — Dependency-aware readiness, health and self-healing

Implement readiness graph for private state, root/kernel capabilities, boot completion, bundled runtime, configuration, `/dev/fuse`, mounted storage targets, network link/type and optional bounded remote probe. Readiness and policy conditions are reported as structured blockers—not one global shell sleep. Track actual mount/proc/RC state and durable mount health: `RUNNING`, `DEGRADED`, `REMOTE_OFFLINE`, `MOUNT_STALE`, `AUTH_ERROR`, `FUSE_ERROR`, `RETRYING`, `STOPPED`.

Build a supervisor that checks desired mounts periodically, distinguishes authentication failure from transport and FUSE errors, uses persistent attempt counters, exponential backoff/capped restart budget and reset-after-stability, and suspends/retries only the affected mount. A working VFS mount with an unreachable remote can stay mounted when safe so cached contents remain usable. Recover stale FUSE only with matching owned process/mount evidence. Restart loops must not create duplicate processes or violate explicit desired stops.

**Acceptance:** Exercise boot-late storage, network class changes, offline/online, auth failures, process crash, FUSE staleness, supervisor/daemon crashes, retry exhaustion and later recovery.

### P07 — Android namespace discovery and truthful visibility

This is a first-class, safety-critical subsystem, not a symlink trick. Inventory `/proc/*/ns/mnt`, `/proc/*/mountinfo`, UIDs and commands; group PIDs by namespace identity and aggregate all members; classify service, root, shell, zygote/USAP, Termux, ordinary app and Android user. Bound scans (source uses 4,096 PIDs and 512 namespaces); mark unreadable or truncated data explicitly. Parse escaped mountinfo fields correctly. Determine exact source ownership using FUSE filesystem, major:minor, root and source identity, while retaining per-namespace mount IDs for owned bind records.

For configured `/storage/emulated/<user>/...` targets, inspect precise per-user alias paths under `/mnt/user/`, `/mnt/androidwritable/` and `/mnt/installer/`. Distinguish `visible_at_target`, `visible_at_alias`, `identity_mismatch`, `not_visible`, and `unavailable`. An alias is **diagnostic only**—it does not prove access at the configured target. A different filesystem occupying the target is a conflict, not an overmount opportunity. Do not invent alias paths across users or assume shell visibility equals app visibility. Report service-only, partially app-visible, no observed app evidence, all **discovered** app namespaces visible, or partial discovery based on actual observation. Maintain per-user observed/accessible/visible counts and be candid about unreadable namespaces, SELinux uncertainty and missing app-level probes.

### P08 — Opt-in, fully owned app-visibility mutation and restart recovery

Implement `namespace.inspect/preview/apply/rollback.preview/rollback/reconcile`. Offer `same-path-bind-v1` only if the live source is owned, target is a recognized Android storage boundary, process has root and `CAP_SYS_ADMIN`, topology is complete/accessible and namespace identity is stable. **Never automatically bind into any namespace shared by zygote, USAP, MediaProvider, ExternalStorage or critical Android storage/system daemons**, even if a harmless-looking app or shell shares it. Aggregate protected reasons over all members. Alias-only and protected gaps disqualify the plan; do not get a green result by dropping affected namespaces.

Recompute plan while holding namespace and mount locks; before `setns`, recheck the target PID namespace ID. Inside target namespace reject symlink, missing/non-directory destination, conflict/overmount and changed mount identities. Record original source and each owned target's namespace ID, mount ID, device, filesystem/root/source signature, user IDs and timestamp in root-private, bounded, no-follow-protected JSON. Apply multiple binds as a transaction: persist each, verify postconditions, unwind only newly made owned binds on failure/cancel/persistence interruption and restore prior ownership state exactly. Rollback or stop detaches only a signature-matching mount. On daemon restart, recover desired visibility, discover newly created app namespaces, prune stale records and fail closed on malformed/tampered ownership data.

**Acceptance:** Source-level tests for forged actions, zygote/MediaProvider protection, alias-only cases, same-path identity, namespace churn, injected bind failure, partial rollback, stale records and multi-user mapping. Device qualification must also make actual file-access attempts under shell, Termux and ordinary app contexts with SELinux and per-user evidence. A unit-test PASS is never an app-access PASS.

### P09 — Resource policies, VFS profiles and bounded cache management

Observe connectivity (`any`, `wifi`, `unmetered`, `offline-allowed`), metering confidence, battery level, charging state, cache free space, boot settle and network settle. Unmetered policy with unknown metering must fail closed. Emit explicit pass/wait/block reasons; avoid aggressive polling, duplicate process launches or forced teardown of otherwise healthy VFS mounts. Integrate policy checks with mount starts/reconcile and job dispatch.

Implement VFS `streaming`, `balanced`, `offline`, `minimal` and `custom`. Expand an explicitly chosen profile to concrete mode/max size/max age/dir cache/poll intervals; custom retains its explicit values. Source example defaults: streaming full/4 GiB/24 h/1 h/15 s; balanced full/2 GiB/12 h/30 m/30 s; offline full/8 GiB/168 h/24 h/1 m; minimal offers small footprint. Provide device RAM/cache-space advisory recommendations, never silent profile rewriting.

Track per-mount cache bytes/files/free/total, maximum, high/low-water thresholds and minimum free space. Supply `status`, `prune.preview/prune`, `clear.preview/clear`, `forget.preview/forget`. Pruning is bounded, chooses older files first, and aims down to low water. Prune/clear/forget run only when the mount is stopped and exact cache tree ownership is verified; clear deletes regular owned contents, forget safely resets the owned tree. Destructive actions require short-lived preview proofs. Reject symlink escapes, root deletion, path traversal and concurrent destructive operations.

**Acceptance:** Policy transition matrix, profile golden cases, low-space behavior, cache symlink attacks, canceled prune and no active-cache deletion.

### P10 — Managed jobs, scheduling and progress

Create a revisioned `jobs/registry-v1.json` with name, enabled, type `sync|copy|check`, source, destination, interval (`every`), network class, charging-only, min battery and destructive sync confirmation. `check` is read-only; `sync` can delete destination objects and requires explicit confirmation before publication and execution as warranted. Reject on-the-fly remote/backend syntax, option-shaped endpoints and arbitrary user-provided rclone flags. Implement `jobs.snapshot/preview/apply/status`, `job.run.preview/run`. Validate jobs under lock, issue proof-bound candidate revisions and maintain per-job durable state (last start/finish/state/error/request ID, run count, next run).

Schedule due work from one daemon scheduler; **persist/claim next run before executing** under per-job lock to suppress duplicate dispatch after daemon restart. Gate dispatch on policy; manual runs use the same safe validation path. Execute exact selected rclone with typed argv; read bounded stdout/stderr/progress, parse bytes/speed/ETA when available; cancel processes safely and journal progress and terminal state. Failed/blocked jobs must have actionable state, not false success.

**Acceptance:** Restart around due time yields at most one claim; one job does not block others; cancellation terminates only its process; destructive sync without confirmation cannot run.

### P11 — Per-mount authenticated rclone RC telemetry

Prepare an endpoint on `127.0.0.1` only for each Skybind-launched mount, with cryptographically random per-instance username/password. Store credentials in root-owned volatile state; remove on stop, restart and daemon recovery. Never hand the WebUI an RC URL, authentication values or generic passthrough. Typed `rc.metrics` queries a fixed allow-list of rclone RC endpoints and returns only transferred bytes, transfer speed, errors, uptime, open files, VFS cache and explicitly supported fields. Missing metrics yield bounded unavailable states rather than fabricated zeros. Reject non-loopback binding, cross-instance access and stale credential records.

**Acceptance:** Port collision, missing RC capability, auth failure, metric parsing, secret leakage canaries, lifecycle cleanup and cross-mount isolation.

### P12 — Remotes, credential handling and rclone crypt creation

Manage the canonical `rclone.conf` as root-private data. Read remote names, type and **credential-free** encryption classification; browse validated configured `remote:path` endpoints by bounded directory listing; return file/folder names and metadata but not config secrets, tokens or arbitrary file contents. Support parent navigation, breadcrumbs, copy path, and source/destination handoff to validated mount/job forms. Manually edited paths invalidate browser-selection provenance.

Provide one **user-defined** Skybind encryption password. CLI accepts it on **stdin**, not argv; browser uses a password input that is not echoed or retained after submission. Store an rclone-obscured representation in private state, never clear text in API/journal/logs/doctor/bundles. Skybind **does not generate the password**, leaves `password2` unset, and refuses crypt creation without an existing password. Supply status, set/replace, revision/generation and non-secret recovery/provenance inventory; changing the password never silently rekeys existing encrypted remotes.

Preview then create rclone crypt wrappers through rclone itself; Skybind never implements file or filename encryption. Default `filename_encryption=standard`, `directory_name_encryption=true`, `filename_encoding=base32`, data encryption on. Supported filename modes `standard|obfuscate|off`; encodings `base32|base64|base32768` (advanced latter two). Reject nested crypt, self-reference, unsupported unsafe options and partial creations; verify the new remote, clean up its failed definition if verification fails. Classify plain and crypt remotes in Browser, Mounts, Jobs and Doctor; warn on unprotected sources/destinations without falsely stating existing objects become encrypted automatically. Provide recovery warning when password generation differs.

**Acceptance:** Secret canary across every transport/artifact; no crypt creation without password; no unintended data encryption implementation; correct wrapper defaults and option validation.

### P13 — Diagnostics, Doctor and sanitized support bundles

Build bounded structured logging for daemon/mount/process, policy, jobs, namespace, RC, WebUI and platform. Include time, severity `DEBUG|INFO|WARN|ERROR`, source, code, sanitized message and suppressed-event counts. Rotate root-owned log files by bytes/backup count. Typed log query supports limit, severity, source, search and follow-style polling. Include runtime log parsing, per-mount tails and safe handling of CLI help/error output. No logs should expose passwords, RC sessions, provider config, sensitive paths or unbounded backend responses.

Doctor returns PASS/INFO/WARN/FAIL checks and actionable guidance for bundled runtime/provenance, config, FUSE, kernel/capabilities, storage/network, policy, mounts, namespaces, jobs, RC, encryption/recovery, package integrity, root-manager transport and platform. Treat expected read-only/static state as informative instead of a spurious warning. Provide one-click deterministic sanitized support ZIP with manifest, bounded structured snapshots, hashes and redaction before export; allow reading only bundles created under the owned support directory. Fail clearly if bundle is incomplete or unsafe.

**Acceptance:** Secret canary throughout exported ZIP, file ownership/modes, bad UTF-8/very large logs, clean diagnostic failure semantics, deterministic contents where claimed.

### P14 — Root-manager integration, hooks and state safety

Support Magisk, KernelSU, KernelSU Next, APatch and conservatively detected compatible module managers. Discover observed capabilities separately: hooks, service, post-fs-data, action, uninstall, embedded WebUI, update staging. Name alone does not prove any capability. Ship `module.prop`, `customize.sh`, `post-fs-data.sh`, `service.sh`, `action.sh`, `uninstall.sh` and small compatibility launchers. Installation verifies files, provenance, permissions and manifest. Post-fs-data initializes state and writes an owned, private platform-ready marker after package verification. Service refuses startup on corrupt package/unusable bundled runtime; starts locked `skybindd` and invokes boot reconcile without replacing native readiness logic. Action launches a one-use authenticated loopback WebUI URL via Android VIEW intent. Keep shell minimal: no second lifecycle engine.

Normal uninstall stops only Skybind-owned processes/mounts, releases only owned namespace binds and erases volatile secrets, **preserving user configuration and cache by default**. An explicit one-shot `purge-on-uninstall` marker may opt into persistent data deletion after path, ownership and safety verification. Missing/corrupt markers and unsafe paths fail closed; never delete unrelated app or system data. Installed post-reboot verification must be distinct from successful root-manager staging.

**Acceptance:** Real/fixture manager capability matrix; staging vs installed identity; corrupted manifest rejection before service; interrupted install; stopped mount and cache remain correct after reinstall; guarded uninstall and explicit purge tests.

### P15 — Two secure WebUI transports, one backend

Carry forward the current `module/webroot` static HTML/CSS/JavaScript/assets directly (not a rewrite), with no CDN/network asset dependency, restrictive CSP, strict output escaping by `textContent`/DOM nodes (never inject backend HTML), bounded requests and backend protocol compatibility checks. Standalone mode binds **IPv4 loopback** at an ephemeral port, issues random single-use expiring bootstrap tokens, then short-lived HttpOnly SameSite=Strict sessions. Mutating routes require CSRF token, exact Origin and Host checks. Add no-store, CSP, frame, referrer, MIME and request/response size/time security headers. Enforce idle lifetime and cleanup of server-owned runtime state. Typed `/api/v1` requests map into the same Engine registry as the CLI.

For managers with a proven compatible embedded bridge, base64url-encode strict protocol requests for a fixed `skybind webui bridge` entrypoint and normalize response/event/error semantics. Detect capability, not just user agent or hostname. Fallback to standalone only if it can really be started; never claim bridge success without backend confirmation. `skybind webui start|serve|bridge` and module Action must expose safe, observable startup. No browser-accessible shell, arbitrary file access or generic rclone RC forwarding.

**Acceptance:** Replayed token, cross-origin mutation, bad CSRF/Host, clickjacking, oversized input, XSS text injection, bridge absence/exception, session expiration and protocol mismatch tests.

### P16 — Preserve and port the existing WebUI essentially as-is (not a redesign)

**Implementation strategy: direct frontend reuse / near-exact visual and interaction parity.** Only former product branding may be surgically changed to Skybind; all other WebUI design and flows must remain effectively identical. The inspected repository already contains the target mobile-first interface. **Copy its current in-scope frontend assets into the recreated repository** and adapt their backend-facing boundaries only as required. Do not commission another UI design system, swap frameworks, restyle screens, reorganize navigation, replace the iconography or labels, change the visual hierarchy, or "improve" flows on subjective preference. A new frontend that merely implements the same features but looks or feels different **fails this phase**. Preserve the visual and behavioral character of the existing Skybind WebUI.

**Original assets and authority (source of truth: inspected `module/webroot/`):**

| File | Preservation policy |
|---|---|
| `index.html` | **Copy** DOM, screen hierarchy, controls, IDs, labels, drawers/sheets, dialogs, wizard stepper, and mobile navigation. Remove ONLY excluded-feature markup and truly orphaned references; preserve all in-scope IDs needed by code/tests. |
| `style.css` | **Copy** original design tokens, actual palettes, light/dark appearance, gradients, cards, borders, shadows, typography, spacing, form components, responsive rules, safe-area insets, motion and focus styles. Prefer leaving CSS unchanged except for justified surgical fixes and removal of unused excluded styles. |
| `app.js` | **Port in-scope view renderers, form handling, event wiring, modal/sheet lifecycles, loading/error/empty states, focus handling, refresh and progress behavior** as closely as possible. Modify backend adapters and strip excluded workflows only. Refactor minimally; behavior parity outranks style/architecture preferences. |
| `model.js` | Carry forward UI candidate normalization, mount row derivation, diff/proof helpers and view-model semantics; remove only excluded helpers. |
| `bridge.js` | Carry forward transport selection, strict request envelope and response normalization where compatible with the new typed API; make targeted security and protocol updates without changing user-visible flows. |
| `icon.png` | Reuse the original icon and its visual identity. |
| `config.json`, `platform.json` | Retain suitable local metadata/bridge configuration and adapt only what the recreated backend/platform legitimately requires. |

Do not replace the vanilla HTML/CSS/ES-module implementation with React, Vue, Tailwind, a component framework, web components, a different router, a new icon library or a redesigned theme without an independently established technical blocker. The preferred first action is **copy the directory**, not hand-redraw the frontend. Keep an immutable reference copy with original hashes and a separate diff against the actively maintained files. Local assets only; preserve existing strict CSP and injection defenses.

**UI/UX parity contract — keep all of this, not just the menu names:**

1. **Shell and global interaction:** same `topbar`, product title and transport indicator; exactly the current five primary destinations **Home, Mounts, Jobs, Activity, More**; fixed, safe-area-aware bottom nav under the existing mobile breakpoint; desktop sidebar and secondary links; same active states, route/view titles, navigation/back behavior, scroll behavior and viewport rules. Respect the observed 760px desktop/mobile boundary and small-phone/narrow-portrait fallbacks. Do not introduce a different nav pattern.
2. **Visual system:** the same dark-first charcoal/blue palette and light-mode variant, radial background, cards, pill badges, semantic severity colors, button treatment, technical monospace values, layout widths, spacing, border radii, progress treatment, hover/pressed/focus/disabled/busy states, and dense-mode styling. Match the real CSS; do not substitute a merely similar aesthetic.
3. **Home:** preserve the current hero and status pill, Runtime/Mounts/FUSE/Network four-card grid, attention notice, two quick-action buttons, Mounts preview, Activity preview and backend-authority/Refresh panel in their existing order, wording style and state transitions.
4. **Mounts:** preserve card format, metadata and badges, refresh/reconcile/rollback toolbar, contextual bottom action sheet and its Start/Stop/Restart/Edit/Activity/Logs/Delete paths, confirmations and refresh state. Reuse the existing **Source → Destination → Behavior → Review** editor UI, stepper, source selector, inline remote browser, remote connection test/manual entry, suggested destination, VFS profile selectors, advanced disclosures, network/power/cache controls, Back/Continue/Review/Apply progression and proof-bound application. Preserve invalid-field timing, sticky actions, unsaved-change confirmation, loading indicators and returned focus.
5. **Jobs:** preserve the scheduled-job cards/list, existing create/edit form, copy/sync/check options, per-job policy inputs, preview-then-apply flow, enable/disable state, run/cancel, next/last run, error banners and confirmations. Do not replace with a generic job table.
6. **Activity:** preserve current operation cards, understandable operation labels, progress/timestamps, cancellation availability, expandable technical details, ordering and refresh/busy states for supported operations only. No unrelated historical-operation controls.
7. **More:** preserve the current destination-card hierarchy and entry behavior for Runtime, Remote browser, Doctor, Logs, Settings. Secondary views must behave as in the source, with desktop equivalents.
8. **Runtime:** preserve current identity/provenance/health presentation, read-only badges, per-mount details, cache/policy/RC information and Android namespace evidence; keep existing preview/confirm interactions where valid. No new capability is implied merely by displaying a button.
9. **Remote browser and crypt creation:** retain remote chips, badges, breadcrumbs, parent navigation, folder rows, contextual remote-item action sheet, endpoint handoff to mount/job forms, password status/entry and crypt-creation modal, with its review/proof/apply behavior. Scope excludes functionality explicitly omitted from this reconstruction.
10. **Doctor and Logs:** preserve severity-colored diagnostic cards, action hints, support export/clipboard; and the dense technical log list with severity/source/search, follow/pause, refresh, visible copy, export, and **clear view** semantics (not backend log deletion).
11. **Settings:** preserve its grouped card/row hierarchy, existing controls and labels for appearance, default page/mount layout, dense mode, reduced motion, refresh/log parameters, session idle, password, diagnostic links and About, with revision-bound Preview/Apply. Ensure the backend accepts precisely the options shown by the UI; resolve mismatch in favor of an explicit product contract, not a hidden altered UI.
12. **Dialog and interaction fidelity:** preserve the sheet vs modal distinction, backdrop, body-scroll behavior, nested confirmation, keyboard Escape/Tab, focus trap and focus return, assistive live announcements, aria-busy/disabled, disabled-until-proof, countdowns/invalidations, spinner/loading labels, empty/error/success messages, manual refresh, polling scoping and device back behavior where applicable. These are UX features, not cosmetic details.

**Explicit exclusions override direct copying.** Any frontend element whose *purpose is solely* an excluded feature must be removed cleanly from the new frontend and its required-operations check. Do **not** carry over code, DOM, API requirements or tests for excluded workflows merely to achieve a byte-for-byte copy. This is a surgical *subtraction* from the current interface, not a license to redesign the remaining interface. Reflow surrounding content naturally, without unrelated visual drift. Preserve crypt **remote creation** and active feature functionality.

**Contract adaptation:** Before editing renderers, enumerate frontend calls from `app.js` and `bridge.js`; map each in-scope call to the recreated backend operation, data schema, supported state and stable error. Put translation in a small API/transport adapter when possible. Remove unsupported operation names from `requiredOperations` rather than making the daemon implement out-of-scope features. Preserve view-state behavior during slow responses, cancellation, stale previews, disconnects and session expiry. Backend authority remains absolute; unchanged UI must not bypass security or validation.

**Working procedure (mandatory):**

1. Freeze the exact current `module/webroot` revision and SHA-256 manifest, preserve its original source/assets, and generate a screen/state inventory.
2. Obtain deterministic reference screenshots and interaction recordings/traces (or repeatable scripted equivalent) across relevant viewports and modes, including dialogs and error states. If the archived source cannot run in a browser harness, build a *read-only fixture responder* solely to expose existing frontend states; do not claim screenshots existed when none were captured.
3. Copy frontend files into the recreated tree. Delete excluded DOM/state/actions surgically; then update only backend/protocol bindings and confirmed regressions.
4. Exercise every navigation action, modal, wizard and input against typed mocked backends before live Android wiring.
5. Compare screenshots side-by-side and with automated visual diffs (stable test data, fonts, DPR, viewport, color scheme, animation disabled); review meaningful pixel differences manually. Also compare click/keyboard/operation traces and accessibility behavior. Visual-only tests cannot catch UX regressions, and automated pixel metrics alone cannot approve them.
6. Require a written exception for each deliberate in-scope deviation: exact baseline behavior, reason, changed files, screenshots before/after, usability impact, security implications and reviewer approval. **Unexplained visual drift or flow changes fail the gate.**

**Reference viewport/state matrix:** 360/390/412px phones, the observed 691px narrow portrait case, 759/760px responsive transition, and 1024px desktop; dark and light mode; dense/default views; enlarged text; reduced motion; portrait/landscape where practical; idle/loading/empty/success/failure; disconnected/expired session; modal/sheet open; software keyboard on forms; long remote names and technical paths. Include Android WebView/embedded manager and standalone-browser transports, not only desktop Chromium.

**P16 acceptance:** Every *in-scope* screen is recognizably the **same WebUI**, with matching design and end-to-end interactions. The original assets are demonstrably reused; the diff consists of scoped deletions, backend bindings and justified fixes. A feature-complete but visually novel frontend is rejected. Each backend operation has the same user-visible loading, success, error, refresh and confirmation behavior in standalone and embedded transports. See the preservation gates in **Section 7**.

### P17 — DevTool, CI, release packages and qualification

Create a single DevTool target for the Go product, a WebUI target and runtime-input source jobs; orchestrate Go unit/integration, protocol/golden/security tests, **WebUI reference screenshot/interaction parity tests**, static JS tests, shell syntax, module contract, package manifest, Python operational fixtures, arm64 toolchain, both runtime-provider packages, installation and device smoke. Use separate gates for **core/lifecycle**, **Android/policy/jobs**, **platform**, **WebUI visual/interaction preservation**, **encryption**, **full-product**, and **device release**. Avoid old tests whose only purpose was removed functionality. A CI source-build workflow must call the currently supported build-time source resolver; do not preserve obsolete CLI subcommands just to keep CI green.

Produce reproducible arm64 release ZIP, checksums, source and helper provenance, SBOM or equivalent dependencies inventory, exact supported capabilities, deployment guide, config reference, known limitations, state retention/uninstall instructions and sanitized support workflow. Version and bind release evidence to exact source commit, archive digest, compiled binaries and test inventory; evidence must not be handwritten PASS labels alone.

Device matrix: at least one real supported Android/arm64 phone with captured manufacturer/model, Android build fingerprint/SDK/release, kernel, root-manager/version/capabilities, runtime/provider variant, rclone version/hash, FUSE helper hash and SELinux mode. Test both packaged runtime variants; qualify Magisk, KernelSU variants and APatch on matching devices where claims are made. Test primary and additional Android users only where available; otherwise explicitly mark not exercised.

Endurance/fault injection includes repeated cold/warm reboot, supervisor kill/restart, service/root-manager restart, multiple mounts/jobs, mobile/Wi-Fi/offline switches, charging/doze/screen-off, low storage/cache pressure, remote outages and auth failures, stale FUSE, storage remount, WebUI idle/close/reopen, app/zygote namespace churn, uninstall preservation and explicit purge, corrupt provenance, symlink/race/ownership attacks and secret canaries. Require **actual file read/write behavior from an ordinary Android app** before an app-visibility claim. Record per-case logs, timestamps, inputs and observed outcomes. Device-unproven behavior must be labeled unqualified, never silently promoted.

**Final seal criteria:** all current-product static contracts pass; both runtime variants have reproducible, integrity-valid packages; all operation and frontend contracts are covered; destructive paths fail closed; real-device required cases and namespace access evidence are attached; zero critical unresolved blockers. Separate an engineering source pass from product/device release approval.

## 4. Dependency graph and critical path

```text
P00 Specification
  -> P01 Foundations -> P02 Packaging/runtime -> P03 Protocol/daemon
  -> P04 Config -> P05 Mount ownership -> P06 Supervisor
             |                 |                |
             +-> P07 Namespace discovery -> P08 Owned binds
             +-> P09 Policy/VFS/cache
             +-> P10 Jobs -> P11 RC metrics
P03 + P02 -> P12 Remote browse/crypt
P03 + P06..P12 -> P13 Doctor/logs
P01 + P02 + P05 + P08 -> P14 Root module/hooks
P00 -> freeze original frontend source and parity fixtures
P03 + P13 + P14 -> P15 Web transports -> P16 Direct UI copy + adapter + parity verification
ALL -> P17 Security, builds, device endurance and release
```

Suggested parallel lanes after P05: Android namespace (P07–P08), resource/cache/job/RC (P09–P11), and remotes/crypt (P12). Integrate them into supervisor and typed protocol before completing the UI. Do not implement a UI-only button before its backend behavior and proof semantics exist. **However, preserve that button and its existing UX from the copied original until the backend is ready**, using a clearly non-production mock/stub in tests, rather than designing a replacement control.

## 5. Persistent schema and operation contracts

| Owned state | Example location | Minimum requirement |
|---|---|---|
| Packaged runtime | `/data/adb/modules/skybind/system/bin/rclone` | executable, same hashed bytes as package provenance |
| FUSE helper | `/data/adb/modules/skybind/system/vendor/bin/fusermount3` | NewFuture origin independently hashed |
| Canonical rclone config | `config/rclone/rclone.conf` | private, selected explicitly for every command |
| Mount config | `config/registry-v2.json` and `previous-v2.json` | revision, digest, atomic durable publication |
| Desired states | `desired/<mount>` | explicit stop persists across reconcile |
| Observed process | `run/mounts/<mount>` | PID + start-time, exact ownership |
| Health/retry | `health/<mount>` | stable health and bounded attempts |
| Namespace binds | `namespace/<mount>.json` | exact source/target signatures, nofollow/size checks |
| Cache | `cache/<mount>` | bounded per-mount owned tree |
| Jobs registry | `jobs/registry-v1.json` | typed job list, revision/digest |
| Job execution | `jobs/state/<name>` | schedule claim, next/last run, result |
| Operation history | `operations/` | start/events/end, interruption reconciliation |
| RC state | `run/rc/` | ephemeral root-private endpoint credentials |
| WebUI state | `run/` and `webui/settings-v1.json` | ephemeral auth vs durable revisioned preferences |
| Logs/support | `logs/`, `diagnostics/support/` | bounded, sanitized, private |
| Platform | `platform/` and `run/platform-ready` | verified boot ingress and guarded uninstall choice |

### Exposed typed API inventory

The appendix below enumerates all 57 directly applicable fixed operations registered in the inspected control engine, grouped by concern, along with operation class. Add no arbitrary shell/argv/filesystem/RC proxy endpoint. A future implementation may refactor names only if CLI, both UI transports and compatibility tests are updated together.


#### Runtime & provider

| Operation | Class | Purpose |
|---|---|---|
| `runtime.status` | query | Inspect canonical bundled runtime/config authority |
| `provider.status` | query | Inspect provider/rclone/FUSE/config readiness |
| `provider.remotes` | query | List configured rclone remotes with credential-free encryption metadata |
| `provider.browse` | query | Browse a configured remote path without exposing credentials |
| `provider.crypt.password.status` | query | Report whether the user-defined Skybind rclone encryption password is configured |
| `provider.crypt.password.set` | run | Store the user-defined Skybind rclone encryption password without returning it |
| `provider.crypt.preview` | preview | Preview creation of an rclone crypt remote using the configured Skybind encryption password |
| `provider.crypt.create` | run | Create and verify an rclone crypt remote using the configured Skybind encryption password |
| `provider.crypt.recovery.status` | query | Report non-secret rclone crypt recovery and password-generation provenance |

#### Config & mount

| Operation | Class | Purpose |
|---|---|---|
| `config.snapshot` | query | Read the credential-free configuration registry |
| `config.validate` | query | Validate a full candidate registry without issuing a mutation proof |
| `config.preview` | preview | Validate a full candidate registry and preview its diff |
| `config.apply` | run | Atomically publish a revision-bound candidate registry |
| `config.previous` | query | Read previous-known-good configuration metadata |
| `config.rollback.preview` | preview | Preview rollback to previous-known-good configuration |
| `config.rollback` | run | Rollback to previous-known-good configuration |
| `mount.list` | query | List configured mount names |
| `mount.status` | query | Read one or all managed mount states |
| `mount.health` | query | Read supervisor health/readiness state |
| `mount.start.preview` | preview | Validate and preview a mount start |
| `mount.start` | run | Start one configured mount |
| `mount.stop` | run | Stop one managed mount |
| `mount.restart` | run | Restart one managed mount |
| `mount.reconcile` | reconcile | Reconcile desired mounts with readiness/recovery state |

#### Health, resources & Android

| Operation | Class | Purpose |
|---|---|---|
| `policy.status` | query | Read resource-policy decisions without changing lifecycle state |
| `vfs.profiles` | query | List named VFS profiles and advisory resource recommendation |
| `cache.status` | query | Read owned VFS cache pressure and limits |
| `cache.prune.preview` | preview | Preview bounded owned-cache pruning |
| `cache.prune` | run | Prune owned cache to configured low-water limits |
| `cache.clear.preview` | preview | Preview owned-cache file clearing |
| `cache.clear` | run | Clear regular files from a stopped mount's owned cache |
| `cache.forget.preview` | preview | Preview complete owned-cache reset |
| `cache.forget` | run | Reset a stopped mount's owned cache tree |
| `namespace.inspect` | query | Inspect Android mount namespace topology and observed visibility |
| `namespace.preview` | preview | Preview app-visibility namespace mutations |
| `namespace.apply` | run | Apply app-visibility namespace mutations transactionally |
| `namespace.rollback.preview` | preview | Preview release of Skybind-owned namespace binds |
| `namespace.rollback` | run | Release Skybind-owned namespace binds and disable app visibility |
| `namespace.reconcile` | reconcile | Reconcile persisted app-visibility intent after namespace churn |

#### Jobs & metrics

| Operation | Class | Purpose |
|---|---|---|
| `jobs.snapshot` | query | Read the typed scheduled-job registry |
| `jobs.preview` | preview | Validate and preview the scheduled-job registry |
| `jobs.apply` | run | Atomically publish the scheduled-job registry |
| `jobs.status` | query | Read persisted scheduled-job execution state |
| `job.run.preview` | preview | Preview a managed rclone job and its policy/destructive status |
| `job.run` | run | Run one allow-listed managed rclone job |
| `rc.metrics` | query | Read allow-listed local-only rclone RC metrics |

#### Operation journal

| Operation | Class | Purpose |
|---|---|---|
| `operation.status` | query | Read persistent operation journal state |
| `operation.list` | query | List persistent operation journal state |
| `operation.cancel` | cancel | Cancel one active request by request_id |

#### Web & platform

| Operation | Class | Purpose |
|---|---|---|
| `doctor.report` | query | Run structured Skybind diagnostics |
| `doctor.bundle` | run | Create a deterministic sanitized support bundle |
| `doctor.bundle.read` | query | Read one Skybind-created bounded support bundle |
| `diagnostics.logs` | query | Read bounded sanitized structured Skybind logs |
| `platform.status` | query | Inspect root-manager capabilities and module integrity |
| `ui.settings` | query | Read persisted WebUI presentation settings |
| `ui.settings.preview` | preview | Validate and preview WebUI settings |
| `ui.settings.apply` | run | Persist preview-bound WebUI settings |

## 6. Non-negotiable quality and completeness checklist

A successful recreation can answer **yes** to all of the following: the package has exactly one verified rclone and the right FUSE helper; managed execution cannot be hijacked; every domain mutation is typed and preview-bound where applicable; state publication survives interruption; process/unmount actions use exact ownership; explicit stop is durable; supervisors and schedulers do not duplicate work; cache and namespace cleanup never touch a stranger; crypt remotes are created only by rclone with user-defined password handling; all exported outputs are redacted; both WebUI transports share one backend; the copied, in-scope original frontend has verified visual and interaction parity; real Android app visibility is qualified by observation; install and uninstall preserve state safely; and release qualification describes precisely what passed and what remains unverified.

**Inspection notes.** The inspected snapshot contains stale documents and automation alongside current code. Specifically, some historical architecture/release pages describe a different runtime relationship, while the active README, static build contract and resolver establish the packaged model. The frontend settings picker offers destination values that the current backend validator does not all accept. Recreate a coherent product contract rather than reproducing these inconsistencies. The Repair 15 namespace source tests passed in this inspection, but its own notes explicitly say Android access and endurance remain device-unqualified.

## 7. WebUI preservation acceptance and source-of-truth manifest

This section is normative. The **current checked-in WebUI is the design specification**, not a sample implementation. The roadmap's "complete UX" requirement means **retaining the original UX**, not reinventing it. Source of truth is `module/webroot` in the inspected full-source snapshot (with current applicable repairs), plus in-scope UX contracts and tests. Snapshot the source again if building from a later verified checkout, and use that explicitly chosen revision consistently rather than mixing UI versions.

### 7.1 Reference source fingerprints

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

### 7.2 Preserve the user's muscle memory

**Pass:** an existing user can find screens, perform tasks, use the same controls, recognize status indicators, open/close the same sheets and navigate the same wizard with essentially the same steps, spacing, hierarchy and feedback. Copy tone of microcopy and exact visual treatment for retained workflows, except wording that would misstate newly verified backend facts.

**Fail:** a new visual theme, new navigation hierarchy, differently sequenced wizard, altered interaction primitives, new framework with changed gestures/focus/scrolling, removed in-scope actions, different confirmation semantics, or an interface "inspired by" rather than cloned from the original. Unjustified differences are bugs.

### 7.3 Preservation verification matrix

| Gate | Evidence |
|---|---|
| Asset provenance | Frozen original hash manifest; committed UI reference; structured original-to-port diff |
| Screen structure | View-by-view DOM/semantic map covering Home, Mounts, Jobs, Activity, More and every secondary screen |
| Visual parity | Before/after screenshots at matched viewport, DPR, palette, typography, data and animation states; diff review |
| Flow parity | Interaction traces for navigation, Add Mount, browse, crypt create, jobs, preview/apply, logs, settings, confirmations |
| State parity | Empty, loading, degraded, disconnected, expired, error, success, canceled and stale-proof behaviors |
| Mobile fidelity | Fixed bottom nav, Android safe areas, 760px breakpoint, 691px portrait, keyboard overlay, no horizontal overflow |
| Accessibility | Focus order, trap/return, live notices, keyboard handling, 44px targets, contrast, reduced motion |
| Backend safety | UI never chooses privileged outcome; typed API and proofs unchanged in semantics; secrets not exposed |
| Scope integrity | No excluded-only controls, backend requirements, handlers, CSS baggage or tests added to the new product |
| Two transports | Identical visual/interaction state and outcomes through both standalone and embedded bridge routes |

**Priority rule:** preserve WebUI visuals and interactions; change **only** what is essential for an in-scope feature to work correctly and securely with the recreated backend. When a genuine incompatibility forces a UI change, first look for an adapter or API change that maintains the existing UI. Explicitly record any necessary user-visible departure rather than silently redesigning it.
