# Devtool — Cumulative qualification workflow improvements

Updated: 2026-10-16; expanded in QW03 performance repair. Protected audit anchor: `Mikeyphw/devtool`, branch `feature/g3r-current-source-evidence` at `f25196a297d42bc3a2ff36a03aa0411f89fe9d46`.

This is the cumulative in-repository improvements ledger. Keep existing findings even after a fix; source changes require a fresh current-commit qualification before being treated as verified on Termux.

## QW-ERG-001 — Remote WAITING state is misclassified as a failed test

- **Status:** Open; diagnostic confirmed, fix not yet implemented.
- **Affected:** `devtool/qualification_workflows.py::main` (`ci24-resume` exit handling), Devtool wrapper/EXO status mapping; `./devtoolw ci24-resume`.
- **Evidence:** Devtool run `65594ec23b72441684c9305e9d5ffc22` returned the valid machine result `state: WAITING_REMOTE`, `ci_verified: false`, `verification.complete: false`, with `run_id: 38843257546`, but then returned exit code 2. Outer Devtool presented `failure kind: test_failure`. GitHub subsequently completed the same run successfully with all 25 jobs successful and 25 artifacts (24 shards plus summary); exact source `f25196a297d42bc3a2ff36a03aa0411f89fe9d46`.
- **Proposed:** Represent `WAITING_REMOTE` as a nonterminal/pending state at the canonical workflow and EXO layers, preserving `ci_verified: false` and blocking `qualify-seal`. Do not turn an incomplete run into a passing qualification merely to suppress a red CLI status. Add pending-state contract and negative tests for failed, missing, tampered, wrong-source, and incomplete GitHub runs.

## QW-SRC-002 — Pre-dispatch source preflight and durable receipt transition ordering

- **Status:** Open; source-inspected, fix not yet implemented.
- **Affected:** `devtool/qualification_workflows.py::ci24_start`; `devtool/actions_dispatch.py::dispatch_workflow`.
- **Evidence:** QW01 implementation creates `DISPATCH_OUTCOME_UNKNOWN` high-level receipt before GitHub preflight; dispatch flow resolves mutable GitHub ref, and the wrapper checks `pre_dispatch_sha` only after dispatch returns. A preflight-only definitive failure can therefore leave a receipt that blocks future attempts, and remote-source drift can create an unnecessary dispatch before detecting mismatch.
- **Proposed:** Perform canonical source/remote identity and workflow preflight **before** dispatch POST; make preflight failures explicitly non-dispatched with auditable receipt transitions, while persisting a durable uncertain record before the non-idempotent POST. Never automatically repeat an uncertain POST or infer correlation from timestamp/branch/SHA alone. Preserve uncorrelated 204 behavior and source-bound fail-closed verification.

## QW-FS03-003 — Nested Devtool final-seal hang under Termux

- **Status:** Fixed and verified on native Termux for commit `f25196a297d42bc3a2ff36a03aa0411f89fe9d46`; full automated seal returned PASS on 2026-10-16.
- **Affected:** QW01 `qualify-seal` and FS03 delegation.
- **Evidence:** Devtool run `407dca103cf24a139ce59779fe34ac92` hit 600-second timeout when spawning `python -m devtool ... final-seal --strict` inside a Devtool invoke. QW01R2 replaced nested process with in-process FS03 audit and passed disposable validation.
- **Follow-up:** Confirmed native run `5da76acd571b4e6eb78d14578d83f387` returned `PASS_AUTOMATED_MILESTONE_ONLY`, FS03 16/16, exit 0, no warnings/errors. Performance investigation separated into QW-PERF-005; maintain native and negative regression coverage.

## QW-PERF-005 — Excessive `qualify-seal` latency and missing stage progress

- **Status:** Open; performance regression/observability gap confirmed, root cause not established. No source repair applied.
- **Affected:** `devtool/qualification_workflows.py::qualify_seal`, `_ci24_evaluate`, `g3r_verify`, `_fs03_strict_in_process`; relevant CI artifact verification and FS03 internal scans; Termux Devtool `test:qual-seal` frontend.
- **Evidence:** Native Termux Devtool run `5da76acd571b4e6eb78d14578d83f387` (2026-10-16) completed successfully on source `f25196a297d42bc3a2ff36a03aa0411f89fe9d46`, with `PASS_AUTOMATED_MILESTONE_ONLY`, CI24 `38843257546` (24 shards), native G3R 13/13, and FS03 16/16. Yet `test:qual-seal` took **850.01 seconds** (total Devtool 861.583 s), emitting no child output and triggering progressless heartbeats roughly once/minute. This run confirms QW01R2 eliminated the previous **600-second nested CLI timeout** but does not establish where the new latency occurs.
- **Source observations:** `qualify_seal()` sequentially calls `ci24_resume()` (remote HTTP + artifact digest verification), `g3r_verify()` (exact-source archive checks), and `_fs03_strict_in_process()` (canonical 16-check audit). FS03 includes target seals and repository cleanup discovery, which can walk a large worktree; none of these are yet timed separately in the wrapper. Their cost remains **hypothetical**, not a diagnosed bottleneck.
- **Proposed:** Record monotonic per-stage durations (`ci24`, `g3r`, `fs03`, total), structured EXO events, progress heartbeats and a clear `last_stage` while retaining exact-source verification, independent rehashing and fail-closed strict checks. Record timing for expensive FS03 sub-checks, and constrain/optimize traversal only after profiling and proving invariant parity. Add synthetic slow-stage tests, timeout/cancellation tests, and Termux-narrow-terminal display coverage. Do **not** bypass evidence verification or treat recorded status alone as authority.
- **Impact:** Reduces opaque 14-minute checks and makes genuine stalls distinguishable from slow work without triggering redundant CI or native G3R.

## QW-TEST-004 — Host-dependent G3R empty-lanes assertion

- **Status:** Fixed in QW01R1 commit `6cf546a472c4f71ee58a362397d0af20d2168d50`.
- **Affected:** `tests/test_g3r_current_source_evidence.py`.
- **Evidence:** Devtool run `13f2b09a848d4f199f6fd2df5f429255` failed on native Termux because `test_missing_native_lanes_fail_closed` assumed the error had to contain `native Termux`, while correct earlier rejection stated `Native/semantic lanes incomplete`. Rollback was successful.
- **Follow-up:** Keep host-independent negative assertions and explicit Termux-emulated coverage.

## Current qualification evidence boundary

- GitHub run [38843257546](https://github.com/Mikeyphw/devtool/actions/runs/38843257546) is `workflow_dispatch`, attempt 1, completed `success`, with all 24 shard jobs and summary job successful and 25 artifacts for SHA `f25196a297d42bc3a2ff36a03aa0411f89fe9d46`.
- Local `ci24-resume` completed independent summary archive verification, and `qualify-status` reported `PASS_CI24_VERIFIED` for the same SHA. Native `g3r-verify` run `91c1793d843e4efcada4da79b85fda3b` accepted 13/13 lanes. Native `qualify-seal` run `5da76acd571b4e6eb78d14578d83f387` returned the authoritative `PASS_AUTOMATED_MILESTONE_ONLY` (FS03 16/16).
- Automated milestone for SHA `f25196a297d42bc3a2ff36a03aa0411f89fe9d46` is **VERIFIED**; formal release qualification remains **false**, carrying `ENV-A06`, `ANDROID-A16`, `DIST-A01`, `DIST-A12`, `DIST-A13`, and `TEST-A11`. Do not rerun CI24/G3R merely to resolve latency or UX issues.


## QW02 / Phase D findings and current dispositions

- **QW-ERG-001 — Implemented, pending native qualification:** `ci24-resume` returns successful observation with `WAITING_REMOTE`, `observation_completed=true`, `qualification_complete=false`, and `ci_verified=false`; failed/mismatched runs still block. Important limitation: outer Devtool test step may show `ok` for a pending observation; use the machine qualification fields, not the exit status, for CI promotion.
- **QW-SRC-002 — Implemented, pending native qualification:** read-only GitHub preflight before dispatch receipt, and `expected_source_sha` enforcement before POST in ACTIONS-02. True transport uncertainty is still sticky; pre-POST source drift has audited retry semantics. Negative mock tests ensure no POST or journal on mismatch.
- **QW-PERF-005 — Instrumented, bottleneck unconfirmed:** flushed progress events and monotonic CI24/G3R/FS03 timings; no shortening or caching of trust gates. Capture timing receipts from the next native qualification before optimizing whichever stage is slow.
- **DIST-SOURCE-006 — Implemented, pending CI:** DIST-G3 SSH/FRX historical-substrate closure uses 14 explicit test-node AST contracts with SHA-256s and original crosswalk disposition evidence. Full test execution remains CI24's authority; static AST checks alone do not certify a successful test run. Historical reports are not runtime gate evidence.
- **RPT-PHASE-D-007 — Four limited retirements:** AOPS02, AOPS03, HROPS01, ROADMAP DELIVERY reports had no literal inbound references in the V110 audit. Their original hashes, lengths, and protected baseline are retained in `docs/HISTORICAL_REPORT_PHASE_D_PROVENANCE.json`, with recovery via immutable Git history. Unknown external consumers are *not* ruled out; the other 53 reports and all 24 compatibility entries remain.
- **Remaining debt:** Full 24-shard CI + native 13-lane G3R, independent verifier, and FS03 seal must execute on the *new* overlay commit. The six real-substrate obligations remain explicitly open. No local disposable test is a claim of remote/native qualification.

## QW03 / QW-PERF-005 — Duplicate CI remote reads and FS03 source-scoped instrumentation

- **Status:** Implemented in source-pinned QW03 overlay against `fe3e215430908de727618ea0bcba3ed92a75487f`; local regression and transaction verification pending final application. **850-second native device latency not yet remeasured.**
- **Affected:** `devtool/qualification_workflows.py` (`_ci24_evaluate`, `_RunScopedClient`, `_ci24_assert_same_remote_run`, `_fs03_strict_in_process`); `devtool/final_seal.py` (`final_seal_report` optional callback), qualification regression tests.
- **Evidence:** Previous CI24 path re-fetched the same GitHub run from `artifact_list`, `download_artifact`, and `verify_download`, despite already verifying that run in `_ci24_evaluate`. This can multiply remote API latency and is unnecessary inside one bounded operation. The current patch makes at most two *direct* remote run identity reads on the verified path (initial and final), retaining downstream existing checks on a detached defensive-copy snapshot. CI jobs, artifact metadata, individual artifact details, registered-archive SHA-256 and ZIP member checks, summary contract, native G3R and FS03 remain required.
- **Negative controls:** Changed run attempt/status/source/workflow on the final authenticated read must block; scoped snapshot cannot be used for a different run/repo; mutated snapshot returned to consumers cannot poison the independent original; missing/bad/tampered artifacts remain fail-closed. Real FS03 generates one progress receipt per completed check; callback exceptions block.
- **Measurement needed:** On native Termux after installing and qualifying *the new SHA*, inspect `stage_durations_seconds` and `ci24.*` / `fs03.*` progress timings. If 850 seconds persists in `g3r`, profile G3R source-manifest file hashing; if within a specific FS03 check, optimize that check without excluding files or weakening the audit; if `ci24`, inspect network latency and artifact registry locks. No release promotion until all six real-substrate obligations are discharged.


## CI24-G8-001 — Frozen G1 source pin needs explicit QW02 amendment

- **Status:** fixed in proposed QW04, pending hosted CI requalification.
- **Evidence:** GitHub run 38852350297, shard 12 `tests/test_actions_g08_g03_amendment.py` and shard 16 `tests/test_actions_g08_qualification.py`: `G8 source contract does not match the pinned post-G7 snapshot`. Original G1 SHA in frozen G8 matrix predates QW02's fail-closed pre-dispatch source check.
- **Resolution:** retain frozen matrix/ledger; accept only checksum-pinned `actions_dispatch.py` with the QW02 source-preflight regression and explicit amendment document. Mutation, symlink, omission and unrelated-source tests reject. No live proof promotion.

## CI24-PROV-002 — Phase D test cannot retrieve ancestor in shallow CI checkout

- **Status:** fixed in proposed QW04, pending hosted CI requalification.
- **Evidence:** GitHub run 38852350297 shard 16: `fatal: path 'AOPS02_ANDROID_EXECUTION_DEVICE_FABRIC_REPORT.md' does not exist in 'f25196a...'`. The report exists in ancestor history but `actions/checkout@v4` default fetch-depth is 1.
- **Resolution:** use `fetch-depth: 0` in hosted shard checkout; preserve SHA-256 and size verification with `git show` against immutable ancestor. Missing ancestor remains a test failure; never replace provenance with nominal filename/hash-only success.


## PHASE-E-008 — OV report-as-proof test migration and nine conservative retirements

- **Status:** implemented in proposed source-bound Phase E overlay; local qualification pending, hosted/native qualification required on resulting commit.
- **Baseline:** `1bb1053f29ba33bf5283244b2badf3f3dccf4581`; historical-report inventory: 53, selected retirements: 9, retained: 44.
- **Root cause:** OV11/12, OV13/14 and OV15/16 tests asserted historical Markdown phrases and obsolete pass counts rather than only checking current executable source. PRES-X02/X03/X05/X06/X07/X08 reports had no literal inbound references and their corresponding independent source proof checks already exist.
- **Resolution:** migrate three tests to inspect the current implementation and supporting tests; preserve tests for real runtime behavior; checksum-pin retired bytes to the immutable baseline and demand Git-ancestor retrieval in CI; preserve all remaining reports/ledgers.
- **Evidence:** `docs/HISTORICAL_REPORT_PHASE_E_AUDIT.json`, `docs/HISTORICAL_REPORT_PHASE_E_PROVENANCE.json`, `tests/test_historical_report_phase_e.py`. Dynamic/external consumers unverified.
- **Follow-up:** maintain 24 public compatibility contracts; run full 24-shard CI, native G3R, FS03 after application. Never infer formal release from source proofs.

## PHASE-E-PERF-009 — Seal latency follow-up pending actual native stage timings

- **Status:** measurement pending; no new speculative speed optimization. QW03 added CI24 network-read deduplication, FS03 check timings, and stage durations.
- **Evidence:** former Termux 850.01-second success on `f25196a`; newest qualified `1bb1053` confirmation provided without the phase-timing output. No defensible numeric before/after comparison is possible yet.
- **Follow-up:** capture `stage_durations_seconds` plus `ci24.*` and `fs03.*` lines from next native seal. Only optimize identified bottleneck; preserve independent archive validation and fail-closed checks.

## PHASE-E02-PERF-010 / QW-PERF-005 — Native 998-second FS03 backup-hygiene scan

- **Status:** Root cause localized; source-pinned Phase E02 performance overlay prepared; native Termux performance qualification pending. No release promotion.
- **Protected source baseline:** `b2bd5f979c54e7287ec6c1f606f7996b275c5639`, CI24 `38875056948` green. All six remaining substrate obligations are unchanged.
- **Native evidence:** Devtool run `68155a42bca64a30a6d6312dd78342c3`, `qualify-seal` on historical commit `1bb1053f29ba33bf5283244b2badf3f3dccf4581`: CI24 7.236s, G3R 0.862s, FS03 1002.461s; FS03 `repository.backup-hygiene` **998.111s**; automated result `PASS_AUTOMATED_MILESTONE_ONLY`, FS03 16/16, total inner stages 1010.789s. Its source differs from the E01 baseline; historical evidence remains pinned to `1bb1053`.
- **Affected:** `devtool/final_seal.py::_workspace_backup_paths`, `devtool/repository_cleanup.py::discover_backup_candidates` and its LIFE-X03 ownership view construction.
- **Root cause:** FS03 uses the general-purpose recursive backup discovery API. It visits every normal project file (including large generated dependency trees), then constructs LIFE ownership for generic file heuristics that cannot be selected (`managed=False` -> `PROTECTED_UNKNOWN`). On Termux this exhaustively traversed/scored unrelated files and/or expensive authority registries.
- **Proposed E02 change:** FS03 uses `discover_backup_candidates(managed_only=True)` with native `find` matching only explicit Devtool-owned backup directory prefixes, root `.git`/`.devtool` pruning, and no per-file stat on irrelevant normal files. If the set is empty, do not construct an empty lifecycle view. Otherwise use the **same** LIFE-X03 ownership/view/planning authority to select candidates. Keep the regular cleanup command and all delete protections intact.
- **Fail-closed:** A failed native scan or timeout blocks strict FS03; a missing `find` uses a strict Python fallback. Never infer PASS from an incomplete result. Managed nested directories remain eligible; generic `*.bak`/`*.orig` files remain protected.
- **Evidence:** Reconstructed source passes 60 focused pytest tests and FS03 16/16. Local Linux synthetic 12,000-file fixture: general discovery 0.386s, managed scan 0.031s; neither is a native Termux prediction. Source and test bundle: `DEVTOOL_PHASE_E02_FS03_BACKUP_SCAN_FAST_b2bd5f9.zip`.
- **Next:** Apply overlay transactionally on exact baseline, repeat CI24/G3R/FS03 once for resulting new commit, compare native `repository.backup-hygiene` timings. If the native managed-directory scan itself exceeds 120s, strict FS03 must report an incomplete scan and require investigation, not grant success.


## RS03 / REAL-SUBSTRATE — Same physical device behind two ADB transports

- **Finding:** RS01/RS02 saw two authorized arm64 Android 16/API36 ADB transports. The operator confirmed these are the **same physical phone**. Transport count must never imply independent device count.
- **Evidence:** RS02 source `0165432df075ec01c720012b8bdcfe21f0c630ce`; TEST-G1 isolation PASS 59.52s, no active device mutation, no SSH run. Branch/source reading showed `AndroidDeviceManager` requires deterministic selection, and `devtool.android.instrumentation._execution_classification` already enforces complete results.
- **Change:** Standalone RS03 read-only inventory, per-invocation HMAC tags, kernel-boot-ID equality dedup where available, non-attributable anonymous receipts, private state, exact transport+runner+expected-package binding, opt-in already-installed `am instrument` test, production output classifier, write-once interruption and final receipts, post-execution identity verification, read-only inspect. No Android install/uninstall/root/reboot or Git mutations.
- **Negative controls:** separate boot IDs never deduplicated, absent boot ID stays indeterminate, unexpected package or changed runner/transport blocks, absent ACK blocks, write-once collision blocks, truncated/crashed/failing tests never PASS, incomplete attempt persists without cleanup or retry.
- **Status:** RS03 code and simulated CLI validated, **device execution pending**. No obligation was discharged. Preserve six IDs `ENV-A06`, `ANDROID-A16`, `DIST-A01`, `DIST-A12`, `DIST-A13`, `TEST-A11` for future reviewed full acceptance.
- **Follow-up:** Run anonymized RS03 survey on native Termux; if a known test suite exists, use one intentionally selected transport and installed runner. Launch distributed qualification only against an independent trusted SSH PC worker; do not treat a second ADB transport as a second worker.

## RS03-PHYSICAL-001 — Two authorized ADB transports are one physical Android instance (verified)
- **Observation:** RS03 read-only native Termux survey, UTC `2026-10-16T15:18:32.899890+00:00`, exact source `0165432df075ec01c720012b8bdcfe21f0c630ce` / tree `bf83832e3d76bc8e7760f885743a77718d6b6237`. Two ADB transport references (`T01`, `T02`) returned `device` and matched by live kernel boot identity. `physical_device_count_verified=1`; no second-device evidence. Earlier `2026-10-16T15:10:38Z` survey had one offline transport and no authorized targets, then recovered without source change.
- **Affected:** Android device selection, transport leases, qualification receipts, RS03 survey/execute.
- **Required:** Distinguish transport IDs from physical device identities, bind active execution to exactly one transport, reject identity drift, and avoid claiming independent device coverage.
- **Status:** PASS for read-only device/runner inventory; active instrumentation NOT_RUN; no R03A obligation discharged.

## RS03-RUNNER-002 — Only observed installed runner belongs to SDVSync, not Devtool
- **Observation:** Both `T01/R01` and `T02/R01` refer to installed `com.sdvsync.test/androidx.test.runner.AndroidJUnitRunner` targeting `com.sdvsync`, as printed locally from the source-bound inventory. No Devtool-specific instrumentation runner appeared in the observed inventories.
- **Affected:** ANDROID-A16 live device workload, result attribution, TEST-A11 live isolation.
- **Required:** Never represent SDVSync test execution as Devtool's own instrumentation qualification. Any SDVSync suite execution requires explicit opt-in because it may mutate the target app's data. Prefer building a disposable dedicated Devtool Android test fixture, with signed/digested APK identities and explicit package/runner scoping, before claiming Devtool Android evidence.
- **Status:** PENDING real Devtool-specific active workload; `ANDROID-A16` and five other carried obligations remain NOT_QUALIFIED.

## RS03-RECOVERY-003 — Environment-scoped RS03 shell variable
- **Observation:** A later Termux shell reported Python could not find `__main__` in repository path when `$RS03` had expired. Reexporting the installed `rs03.py` absolute path resolved invocation.
- **Affected:** Standalone RS03 installation/CLI ergonomics.
- **Required:** Add an executable install/wrapper command rather than relying on an ephemeral shell variable; preserve Zsh-compatible command paths.
- **Status:** Documented workaround; source improvement pending.

## RS04 / SUBSTRATE-ANDROID-004 — Disposable canonical AOPS03 physical-device fixture

- **Status:** Implemented in standalone, SHA-256-manifested RS04 bundle; synthetic regression successful, native build and execution PENDING on user Termux.
- **Source:** `0165432df075ec01c720012b8bdcfe21f0c630ce`, tree `bf83832e3d76bc8e7760f885743a77718d6b6237`, Android 16 API 36, one physical device behind two verified kernel-identical ADB transports.
- **Problem:** RS03 discovered only the `com.sdvsync` installed instrumentation runner. Executing unrelated app tests does not validate Devtool's own canonical Android installation/lease/cleanup flow and may affect its app data.
- **Implementation:** Separate disposable Gradle project with pinned Android Gradle Plugin 9.3.1, compile SDK 36 and no AndroidX test dependency. A platform Instrumentation subclass provides two read-only checks and optional deliberately failed check. RS04 prepares one private work directory, defaults to offline Gradle build, SHA-256 binds the source/APK pair and HMAC-binds a selected RS03 transport/boot identity, then opt-in invokes production `devtool.android_instrumentation` canonical AOPS03 entrypoint with exact serial, required policy and `--cleanup-app`.
- **Safety:** Never install or replace any package that already exists with either fixture package ID; no unrelated application, signing identity, root operation or device reboot is requested. Installation and Devtool-managed cleanup require separate explicit flags; before/after checks require package absence and unchanged kernel identity. Persistent `STARTED_UNVERIFIED` prevents blind retry after interruption. Private logs may contain serials, kept in 0700/0600 location; public results sanitize them.
- **Evidence so far:** 20 standalone synthetic regression tests passed with zero warnings, including deliberate negative classification and cleanup failure. Android Gradle build and live device execution not performed in the assistant environment. This provides a bounded next step for `ANDROID-A16` and `TEST-A11`, but closes zero formal obligations.
- **Follow-up:** Evaluate `build.result.json` and sanitized `execute.result.json`, investigate any fail-closed reason against the actual Termux environment, then map real outcomes to original authoritative obligation acceptance criteria. Next independent SSH worker phase should use a real PC (not another transport to the same phone).

## RS04-LIVE-017 — Real AOPS03 positive instrumentation passed (2026-10-16)

- **Status:** Observed PASS from user-provided on-device RS04-R1 summary; private raw receipts not independently downloaded.
- **Source:** `0165432df075ec01c720012b8bdcfe21f0c630ce` / tree `bf83832e3d76bc8e7760f885743a77718d6b6237`; original private workspace `rs04-20261016T153946Z`.
- **Evidence:** Offline Gradle build `289.147s`, both APKs; read-only package absence preflight PASS after Android 16 `pm path` fix; canonical AOPS03 ran 2/2 tests successfully, cleanup `passed`, packages absent, kernel boot identity `UNCHANGED`.
- **Boundary:** One physical device exposed through **two** ADB transports, not two independent Android devices. This does not close `ANDROID-A16` or any carried obligation; do not claim a signed formal release. Retain the positive receipt and do not reuse its write-once workspace.

## RS05-NEG-018 — Controlled, source-bound failure attribution without redundant Gradle build

- **Status:** Standalone RS05 fork helper implemented; 11 focused regressions pass; combined RS04-R1+RS05 suite **41 passed** (local synthetic tests). Native negative-control execution not yet provided by user.
- **Root issue:** RS04 originally supports `--negative-control` but refuses a second execution in the already-successful write-once workspace. A new workspace normally repeats Gradle packaging despite two verified APKs already existing.
- **Resolution:** A separate helper SHA-pins the installed RS04-R1 script, verifies the original successful positive execution and cleanup receipts, verifies source/fixture/APK SHA-256, reads current kernel identity, protects fixture package names across Android user profiles, and copies only immutable source/APKs into a new private write-once workspace. It prepares an RS04-compatible, explicitly provenance-linked build receipt without running Gradle. Execution remains a separate opt-in RS04 `execute --negative-control` using canonical AOPS03/DeviceLease/cleanup. A previous interrupted execution or changed installed package never triggers automatic retry or deletion.
- **Negative expectations:** Original classifier must return `test-failure`, 2 executed / 1 passed / 1 failed; successful fixture cleanup and stable device identity are separately required. A negative run that reports success without failing a test, or leaves an installed fixture, must block.
- **Scope:** No source mutation or CI dispatch; not a release gate on its own. User-provided live result required. SSH multi-host work is next after controlled negative proof.

## RS05-LIVE-NEG-006 — Canonical AOPS03 physical-device negative test and cleanup verified

- **Status:** PASS for the bounded Android negative workload; full `ANDROID-A16` / `TEST-A11` acceptance still NOT_QUALIFIED.
- **Source identity:** Native Termux Devtool SHA `0165432df075ec01c720012b8bdcfe21f0c630ce`, tree `bf83832e3d76bc8e7760f885743a77718d6b6237` (tracked clean, untracked not inspected).
- **Evidence supplied by operator:** RS04 positive fixture passed 2/2 and cleaned both APK packages. RS05 workdir suffix `rs05-20261016T172836Z` successfully forked already-built SHA-pinned APK pair, verified positive receipt and no preexisting fixture packages, and completed deliberately failing 2-test Android instrumentation on the same verified physical phone. AOPS03 `canonical_status=failed`, `canonical_failure_kind=test-failure`, test counts 1 PASS / 1 FAIL, process exit 1; top-level negative control `status=PASS` because correct failure classification and cleanup were observed. `canonical_cleanup_status=passed`, both packages absent, post-identity UNCHANGED, ~22.132s. Raw orchestrator output not included; SHA-256 evidence reported by operator.
- **Affected:** Android instrumentation, test result truthfulness, device lease/selection, failure classification, protected cleanup and recovery.
- **Recommendation:** Preserve source/fixture hashes and write-once receipts. Do not promote the six carried formal obligations on positive+negative isolated AOPS03 results alone. Do not rerun Gradle build, negative suite, or 24-shard CI to establish already-observed evidence.

## RS06-SSH-007 — Independent physical SSH worker readiness before remote lifecycle gates

- **Status:** RS06 implementation locally tested, native Termux/independent remote evidence PENDING. No real SSH worker was available or contacted by the assistant.
- **Finding:** RS01/RS02 showed SSH tools available locally, but no actual remote substrate (`ssh.requested=false`). Two ADB transports are the *same* kernel-verified phone and cannot count as independent distributed coverage. Devtool's production `ssh_qualification.qualify_worker` validates managed sync, detached tmux, rsync return, second clean sync and optional project validation, but live execution requires explicit verified remote worker configuration.
- **Source inspection:** Devtool SHA `0165432`; `devtool/ssh_profiles.py::list_profiles`, `devtool/ssh_qualification.py::qualify_worker`, `docs/SSH_REMOTE_EXECUTION.md`.
- **RS06 implementation:** Standalone read-only local profile-count and strict SSH probe. Exact SHA/tree/tracked cleanliness, SSH known-host enforcement, no host key TOFU, sanitized host/tool/identity evidence, local/remote Linux kernel boot comparison, reject self-SSH, no remote data mutation/sync/bootstrap/tmux/cleanup, exclusive private receipts, 11 regression tests.
- **Next:** Gather `rs06-survey` and, when operator has an existing independently trusted SSH PC, optional `rs06-ssh` receipt. Then run Devtool-native `ssh doctor`, `ssh prepare --dry-run`, and reviewed managed worker dry-run before any live lifecycle qualification. `DIST-A01`, `DIST-A12`, `DIST-A13`, and the other 3 obligations remain NOT_QUALIFIED.


## RS06-R1 — Local current SHA diverged from older SSH preflight pin

- **Status:** source-bound read-only preflight repinned to operator-observed local SHA; GitHub attestation **not** established. No formal obligation closed.
- **Evidence:** RS06 JSON reported local commit `75d524dd81e9b2cd9c4bce9d27a15fca3712f9e2`, tree `5473aff7a0f067f64b50683ea3f25e74d181273f`, tracked clean, but original RS06 expected `0165432df075ec01c720012b8bdcfe21f0c630ce`. GitHub branch remained on `0165432` and did not expose the local commit. Report still said `ssh.reason_code=no_ssh_alias_selected`, because survey did not invoke SSH.
- **Resolution:** separate RS06-R1 artifact pins precisely the operator's local commit and tree; preserves the immutable original RS06 archive; improves not-run reason on source-blocked reports; tests exact SHA+tree, mismatch blocks SSH, and retained SSH identity/host-key/privacy guards.
- **Follow-up:** run noninteractive strict-host-key SSH `mom` and RS06-R1 probe; capture tool availability and independent kernel identity. Promote Devtool source only after independent remote/source qualification, not from this local-only receipt.

## RS07 — Native SSH doctor/prepare gate before distributed source synchronization

- **Status:** standalone, locally regression-tested (21/21) and packaged; **live Termux SSH `mom` result pending**. No repository source change or obligations discharged.
- **Evidence:** RS04 real AOPS03 positive tests 2/2 and cleanup PASS on `0165432df075ec01c720012b8bdcfe21f0c630ce`; RS05 controlled negative 1/1 failure classified `test-failure`, cleanup PASS; RS06 survey reported a different local commit `75d524dd81e9b2cd9c4bce9d27a15fca3712f9e2` (tree `5473aff7a0f067f64b50683ea3f25e74d181273f`) and did not run SSH probe. GitHub did not attest the newer local commit. SSH aliases and Devtool profile both named `mom`, but remote readiness and host independence have not yet been proven.
- **Affected:** Devtool SSH profiles (`ssh_profiles`), `ssh doctor`, `ssh prepare --dry-run`, `ssh qualify --dry-run`, remote host identity, managed workspace and source sync safety, DIST-A01/DIST-A12/DIST-A13 investigation.
- **Why:** An SSH alias and a same-named Devtool profile might target different machines; raw CLI exit status alone does not establish healthy remote worker, safe workspace policy or trust. A second phone SSH endpoint cannot count as a separate worker.
- **Action:** RS07 checks RS06-R1 independent boot identity, strict saved host-key authentication, configured remote tools, exact Devtool profile resolution, native doctor + dry-run prepare, managed worktree constraints, capacity; optional dry-run `ssh qualify` creates sync plan. Fail-closed on missing, mismatched or malformed evidence. Restrict output to private write-once JSON and hashes; do not save remote hostnames/identities.
- **Status/limits:** 21 deterministic Python negative/positive regression tests passed on a mocked host. Genuine PC result **not executed yet**. Dynamic Git config and untracked-file cleanliness are not claimed. RS07 readiness is not authoritative closure of any six carried obligations; source remote attestation and original per-ID acceptance criteria remain outstanding.
- **Follow-up:** obtain RS07 JSON, inspect exact managed workspace and sync exclusions, then create a separate explicitly authorized live native `ssh qualify --no-bootstrap` with synchronized source, detached tmux/return artifacts and protected recovery. Never run live remote changes from an unverified read-only plan.


## RS07-R1 — Source pin drift incorrectly labeled as SSH independence failure

- **Status:** addressed in standalone RS07-R1 (source-independent repository artifacts untouched); real `mom` readiness pending.
- **Evidence:** Operator RS07 JSON on 2026-10-16: `source.commit=0165432df075ec01c720012b8bdcfe21f0c630ce`, tree `bf83832e3d76bc8e7760f885743a77718d6b6237`, tracked clean; bundled RS06/RS07 expected `75d524dd81e9b2cd9c4bce9d27a15fca3712f9e2` / tree `5473aff7a0f067f64b50683ea3f25e74d181273f`. The collector returned `rs06_independent_worker_not_verified` and never attempted SSH/doctor/prepare. The previous local-only commit could not be verified on GitHub; the actual 0165432 commit/tree was independently confirmed from the remote branch.
- **Change:** pin both embedded RS06 and RS07 archive to 0165432 and its exact tree; propagate approved RS06 source/auth/identity error codes instead of falsely diagnosing host independence. Keep strict host key checks, same-kernel rejection, exclusive evidence files, worker profile policy, zero remote mutations and no false formal-release closure.
- **Tests:** 25 targeted safety regressions, including new source-pin, source-failure, auth-failure and same-host reason attribution tests. **Pending:** native `mom` readiness outcome; `DIST-A01`, `DIST-A12`, `DIST-A13` remain NOT_QUALIFIED.

## RS07-ENDPOINT-001 — Redacted effective endpoint mismatch diagnosis (2026-10-16)

- **Status:** Observed real-substrate blocker, diagnostic implemented; underlying local configuration pending inspection.
- **Evidence:** Real RS07-R1 output `rs07-r1-sync-20261016T193105Z.json` at source `0165432df075ec01c720012b8bdcfe21f0c630ce` reports `independence=VERIFIED_DISTINCT_KERNEL_BOOT`, doctor `healthy=true`, `host_identity_state=recorded`, `workspace_mode=managed`, `capacity_verified=true`, `ssh_ready_tool_count=5`, but `reason_code=devtool_profile_endpoint_not_verified_as_same_ssh_alias`. Prepare and qualification dry-run remain `NOT_RUN`.
- **Root cause boundary:** RS07 compares effective SSH `hostname`, `user` and `port` from `ssh -G mom` against `ssh -G` with Devtool profile's host, forced user and forced port. Sanitized RS07 response doesn't identify which field differs. A discrepancy could be a real profile misconfiguration. Do not assume or bypass it.
- **Affected projects:** Devtool SSH profile `mom`, Termux/OpenSSH alias `mom`, RS06/RS07 qualification scripts, release substrate DIST-A01 / DIST-A12 / DIST-A13.
- **Improvement:** Add separate read-only, redacted local endpoint diagnostics, distinguishing host/user/port mismatches from a trusted independent remote, without running remote commands or printing addresses/usernames. This standalone diagnostic provides comparison booleans, profile scope, mode, and workspace mode; never changes profile/SSH configuration or asserts release qualification.
- **Remediation:** Align the existing Devtool `mom` profile host/user/port with the trusted `ssh -G mom` result, while preserving managed workspace config, strict host-key policy and key. Rerun RS07-R1 with an unused output path. After dry-runs pass, review live `ssh qualify` effects before enabling source sync.
- **Regression evidence:** `tests/test_endpoint_diagnose.py` verifies 19 cases: exact equality, host/user/port mismatches, all mismatches, missing profile, invalid operands, JSON parsing, redaction, 0600 write-once, and non-mutating command shape.
- **Acceptance state:** Not a formal DIST obligation discharge. Do not promote readiness until live source-bound worker qualification meets original acceptance criteria.


## RS07-TERMUX-USERNAME-002 — Username-only SSH alias mismatch on single-user Termux sshd

- **Status:** Fix implemented in standalone RS07-R2; focused local regressions pass; real `mom` worker retry PENDING. No Devtool tracked file was changed. All six original release obligations remain NOT_QUALIFIED.
- **Source:** GitHub-verified SHA `0165432df075ec01c720012b8bdcfe21f0c630ce`, Git tree `bf83832e3d76bc8e7760f885743a77718d6b6237` on Termux controller.
- **Observed substrate:** Operator-provided D1 report: effective OpenSSH vs Devtool `mom` comparison returned `hostname_match=true`, `port_match=true`, `user_match=false`. Earlier RS07-R1 proved `VERIFIED_DISTINCT_KERNEL_BOOT`; native doctor healthy, host identity recorded, capacity verified, managed workspace, five worker tools. Prepare/dry-run not reached due to string-equality gate.
- **Root cause:** Termux's patched OpenSSH server permits arbitrary login user strings and authenticates to its single Android app UID. Exact SSH `user` equality is a valid default for ordinary Unix SSH servers but is overly strict for this *verified* class of server. Upstream confirmation: https://github.com/termux/termux-app/issues/3582 and https://github.com/termux/termux-packages/discussions/18318.
- **Resolution:** Preserve the exact hostname+port comparison and RS06 independently verified distinct kernel boot. For a native doctor-probed `platform=termux` with canonical Termux app HOME only, perform two separate read-only, noninteractive, StrictHostKeyChecking=yes SSH identity probes through the same trusted alias (one normal; one with the profile's username and port forced), and require the *same* non-root Android UID, same Termux home path and same boot UUID. Cross-check doctor-reported home. Fail closed on any SSH login failure, missing/truncated/spurious output, changed UID/home/boot, wrong port/host, unrecognized home, or non-Termux worker. Never waive user differences on ordinary Linux servers.
- **Effects / privacy:** Commands are read-only (id, HOME, /proc/sys/kernel/random/boot_id); no SSH key/config rewrite, no remote installation/sync/tmux/cleanup, no login prompts, no raw user, host, UID, home or boot identity in shareable receipt. Native doctor may persist *local-only* provider evidence as before. Every receipt is private write-once and source pinned. A waiver reports only `endpoint_auth_equivalence=termux_verified_same_uid_home_boot_for_both_login_names`.
- **Tests:** Original 25 RS07 regressions plus 17 Termux equivalence regression cases and 19 D1 endpoint diagnostics. Live `mom` result not yet observed; don't promote DIST obligations or skip the managed sync dry-run.
- **Recommendation:** Adjust Devtool core SSH profile/worker endpoint identity semantics in a future source-bound overlay: use verified remote account+host identity rather than exact presented SSH username for Termux sshd; retain strict username check elsewhere. Preserve this finding in the cumulative improvements ledger when upgrading the source. Avoid GitHub CI24/G3R churn for a standalone preflight helper.

## RS07-WS-004 — Managed synchronization deletion false-positive and scoped review (2026-10-16)

- **Status:** mitigated in standalone RS07-R3, pending live user-device verification; Devtool repository unchanged.
- **Observed evidence:** RS07-R2 receipt 2026-10-16T20:04:15Z on pinned clean `0165432df075ec01c720012b8bdcfe21f0c630ce` reported independent Termux host, authenticated same UID/HOME/kernel boot despite SSH username strings, Devtool doctor `healthy=true`, recorded host key, capacity verified, 5/5 SSH tools; blocked `managed_workspace_sync_delete_needs_review`, native prepare/sync plan NOT_RUN. The previous RS07 validator rejected *any* `sync_delete=true`.
- **Root cause:** Devtool `devtool/ssh_tmux_runner.py` defaults `sync_delete=true` for managed/ephemeral workspaces, and `devtool/ssh_workspace.py` explicitly enforces managed-workspace scoping, marker ownership, symlink/path/canonical containment, leases, and `--delete-delay`. The RS07 blanket rejection was a false positive for safe owned, scoped workspaces and incorrectly prevented examining the native sync plan.
- **Fix in standalone RS07-R3:** After source-pin, independent kernel, strict host identity, matching/equivalent Termux endpoint, capacity/health/mode checks, call only Devtool `ssh workspace PROFILE --format json` and `ssh sync PROFILE --dry-run --format json`. Verify reported remote HOME, workspace root strictly inside HOME, workspace path strictly below the root, canonical paths and symlink status, ownership marker for pre-existing workspace, exact matching workspace identity and deletion policy between status and plan, and reject any `*deleting` or unknown rsync special changes. Permits the normal managed deletion configuration only if there are **zero proposed deletions**. Never enable/delete automatically. Preserve sanitized change counts, source transport and hashes; do not save filenames/destinations. Existing `ssh prepare --dry-run` and optional `ssh qualify --dry-run --no-bootstrap` remain gated. Workspaces that require legitimate deletions need explicit operator review in a separate phase.
- **Validation:** 84/84 Python regression tests pass (original and added R3 tests). Source/AOS03, RS04, RS05 and Devtool qualification states unchanged. No user-device live R3 result yet. Formal release remains unqualified; six original real-substrate obligations remain open.
- **Recommendation:** Move reviewed managed-sync-delete checks into Devtool's authoritative source-bound SSH qualification acceptance criteria, not as a permanent wrapper-only workaround. Never treat a `delete=true` flag alone as a failure or assume a dry-run proves safe later execution without destination revalidation.



## SKY-DV-001 — Skybind source still bypasses native Go test/lint runner

- **Status:** Confirmed source adoption opportunity; implementation NOT_STARTED.
- **Source evidence:** Devtool archived HEAD `5cfcd3cce55cf2e5a1a3663fcbb12d0a80b9bd82`, `devtool/project_runners.py::GoRunner` builds native `go test -json`, `go vet`, restore/build/package, progress parsing and toolchain identity; Skybind 2026-10-16 `.devtool.toml` declares `[targets.skybind] runner="command"` with Python/bash command jobs for most Go-related operations.
- **Affected:** Skybind source tests, CI work planning, Devtool native Go runner.
- **Recommendation:** Add a separate `skybind_go` target for ordinary Go source test/lint. Preserve specialized source-bound KernelSU packaging and Q/Personal release authority. Verify provider/toolchain and runs natively before migrating any existing contract.

## SKY-DV-002 — Too many one-step workflows, not enough reusable DAG composition

- **Status:** Confirmed; design proposed, not implemented.
- **Evidence:** Skybind `.devtool.toml` parses to 6 targets, 80 target-local jobs, 84 workflows, 66 wrapper commands; **80 workflows contain one step**, only four contain multiple nodes. Devtool `workflow_runtime.py` expands cross-target `target:<target>#<action>` natively and deduplicates prerequisites; `workflow_config.py` preserves owner-scoped job identities.
- **Affected:** Skybind unified API R0-R6, BKX, chrootctl, native Android work, release evidence.
- **Recommendation:** Retain the existing entrypoints, add a small `r0-compat` → `r1-source` → `r1-android-readonly` → `r1-acceptance` DAG hierarchy rather than more ad-hoc nested scripts. BKX and chrootctl offline source/CLI fixtures should be separate target-owned jobs, not copied test logic. Use one EXO execution identity per node, with source-bound JSON evidence.

## SKY-DV-003 — Local device resource serialization differs from federation budget

- **Status:** Confirmed policy gap; no observed race; open.
- **Evidence:** Skybind `[workspace.scheduler].max_android_device=1`; Devtool uses this field in `devtool/federation_scheduler.py`, while local `devtool/workflow_scheduler.py::_resource_allowed` handles Gradle/.NET resource caps and `device-exclusive` resource class, **not** `max_android_device`. Skybind existing ADB/device jobs do not declare `metadata.resource_class="device-exclusive"` or `global_reservations`. Local parallelism is disabled by default, so no active concurrency failure claimed.
- **Affected:** Skybind physical device acceptance, native instrumentation, release provenance; Devtool local DAG documentation and config diagnostics.
- **Recommendation:** Declare explicit device-exclusive resource identity for every device/installed-module touching node, retain sequential default, test same-physical-device two-transport case, and establish true cross-process device leasing before concurrent acceptance. Consider Devtool doctor warning when `max_android_device` is configured in a non-federated workspace but can't constrain local workflow waves.

## SKY-DV-004 — Ambiguous `read_only` metadata conflates API semantics with repository writes

- **Status:** Reproduced by source planner; classification/annotation fix not implemented.
- **Evidence:** Skybind `skybind_android_device.api-device-readonly` declares `metadata.read_only=true` while its outputs include `build/evidence/android/api/**`. Read-only `devtool plan` showed simultaneously `read_only=true`, `writes=["build/evidence/android/api"]`, `writes_known=true`. In `workflow_scheduler.py::scope_for_graph_node`, `read_only` marks repository write-free scheduling eligibility; it does not mean the product API uses read-only RPCs.
- **Affected:** Skybind device receipts, Devtool scheduling safety metadata.
- **Recommendation:** Use `api_mutation=false` for RPC meaning; set `metadata.read_only` only on genuinely repository-write-free jobs. Preserve exact evidence output scopes. Add a preflight diagnostic for contradictory `read_only=true` plus nonempty outputs (consider explicit exceptions only when semantics provably disjoint).

## SKY-DV-005 — Six unknown-write jobs remain conservatively serialized

- **Status:** Inventory confirmed; benign by default, output-scope audit open.
- **Evidence:** No explicit `outputs` and no true `metadata.read_only` for `skybind.diagnostics-transports-source`, `skybind.q05p5-webui-runtime-diagnostics`, `skybind_release.q11-reconcile`, `skybind_release.q14-attestation`, `skybind_release.q17-negative-run`, `skybind_app_probe.install`. Devtool scheduler correctly treats an unknown write set as repository-exclusive.
- **Affected:** Skybind planning concurrency / Termux resource efficiency.
- **Recommendation:** Review actual side effects and update complete output sets only where true. Device installation remains exclusively reserved regardless of repository output location. Do not label a mutating job read-only solely to make it parallel.

## SKY-DV-006 — Wrapper seal mismatch against archived Devtool snapshot

- **Status:** Reproduced in extracted archive; live Termux pinned-runtime qualification REQUIRED before repair.
- **Evidence:** Read-only `wrapper seal --json` exited 1 when inspecting Skybind with Devtool archive HEAD `5cfcd3...`; `devtoolw` reported drifted, and `docs/WRAPPER.md` missing. The generic canonical bridge/EXO provenance self-test passed. This is an **archive pairing** observation, not proof the installed Skybind runtime is broken.
- **Affected:** Skybind `devtoolw` wrapper contract, Devtool version locking, docs.
- **Recommendation:** Compare live `wrapper status/describe/seal` to Skybind's `.devtool-wrapper.lock`; update managed launcher only with reviewed installer, preserve custom Zsh/Termux ergonomics; supply project-local wrapper guide; do not claim seal PASS yet.

## SKY-DV-007 — Default-target preflight gives misleading failures without explicit owner target

- **Status:** Reproduced usability issue; not a parser defect.
- **Evidence:** `devtool preflight --workflow api-device-readonly --json` resolved default target `skybind` and reported `No command configured for action`; selecting `--target skybind_android_device` resolved its target-local job. Targeted preflight on desktop reported expected `native-termux`/`desktop-linux` incompatibility. Targeted `plan` passed and displayed one sequential execution wave.
- **Affected:** Skybind developer docs, Devtool preflight UX, wrapper discovery.
- **Recommendation:** Use wrapper entrypoints or explicit target in all recipes; treat environment mismatch as not runnable on the inspection host. Optionally add preflight hint `workflow found on target: skybind_android_device` when default target resolution fails.

## SKY-DV-008 — Native Android + source-bound remote artifact chain can reuse Devtool primitives

- **Status:** Proposed integration, NOT_STARTED.
- **Evidence:** Devtool `devtool/android*`, `actions_dispatch.py`, `actions_pipeline.py`, `run_store.py`, `wrapper_launcher.py`, and source-generated docs already implement native Android operations, exact remote run head SHA checks, restart-safe dispatch receipts, artifact hashing, and EXO provenance. Skybind's current app probe target uses an Android runner but a full native management app/test APK is not present in this source snapshot.
- **Affected:** Skybind native app, BKX/chrootctl R0-R6 acceptance, GitHub Actions, Devtool evidence reports.
- **Recommendation:** Reuse Devtool's native Android build/device and Actions collector. Add separate source-bound acceptance receipts for actual UID/grants/protocol denials; never promote release from successful command exit or an accepted remote dispatch. Keep WebView BLOCKED and reboot PREPARED labels truthful and preserve six open Devtool real-substrate obligations.

## SKY-DV-009 — Avoid repeating completed qualifications when optimizing workflows

- **Status:** Standing integrity guard, identified as cross-project operational risk.
- **Evidence:** Devtool's qualification wrapper and durable run receipt paths distinguish pending CI, accepted dispatch, verified CI artifacts, native G3R lanes and formal release state; the cumulative ledger already records QW-PERF-005 and Phase E02 performance work. Re-issuing CI24/G3R on unchanged SHA to diagnose UX would waste resources and conflate new source qualification with existing evidence.
- **Affected:** Devtool and Skybind qualifications on Termux.
- **Recommendation:** Pin each evidence receipt to exact source/run/artifact identities, consume prior qualified evidence only within matching scopes; profile the remaining measured bottleneck rather than blind reruns. New commits require their own source-bound CI and native qualification; pending/blocked aren't PASS.

**Study deliverable:** `DEVTOOL_SOURCE_STUDY_SKYBIND_OPTIMIZATION_20261016.md`; original cumulative findings above preserved unchanged; this append is source-review evidence, not a change to checked-in Devtool/Skybind repositories.


## SKY-DV-010 — Project-specific remote-only Android build policy

- **Status:** User policy confirmed; implementation NOT_STARTED. Supersedes local-build portion of SKY-DV-008 only; native Devtool Android support itself is not defective.
- **Evidence:** Skybind user on 2026-10-16 explicitly requires Android app builds *only* through GitHub Actions and accepts unstable interim Skybind revisions until the complete unified roadmap ships. Archived Skybind `.github/workflows` had source/provenance/module paths but no dedicated `skybind-android-apks.yml` for the future native app; `android-app/` not implemented. Devtool has Actions dispatch/resume and independent Android device test capabilities.
- **Affected:** Skybind Kotlin/Compose APK and instrumentation APK, `skybind_app_probe` target and future Android target, Devtool wrappers/DAG/EXO, GitHub Actions and device acceptance.
- **Recommendation:** Add hosted Android build+instrumentation workflow with source-run-artifact-certificate manifest; local Devtool only dispatches/resumes/verifies/installs/tests those exact bytes. Flag or disable local Android build wrapper entries in Skybind. No local `assemble*`, APK signing, Gradle build fallback. Separate CI_BUILD_VERIFIED from DEVICE_ACCEPTED and formal release. Continue local Go/Python source checks; don't use this as a reason to disable Devtool's generic Android build runner in other repos.

## SKY-DV-011 — Roadmap batching and historical WebView noncritical-path policy

- **Status:** Plan updated; no underlying code changes.
- **Evidence:** User not relying on Skybind until full roadmap completion and explicitly tolerates development instability; earlier historical WebView V8/V9/V10 evidence remains partially blocked, while A1–B3 backend checks are historically green.
- **Affected:** Skybind A1–E / R0–R6 development, Devtool acceptance DAGs, native app migration, final E5 release scope.
- **Recommendation:** Combine source/contracts, broker, consumer adapters, native UI and hosted CI work into larger dependency-aware DAG development batches. Internal backward compatibility of unshipped Skybind can break; preserve frozen CFS1 and BKX/chrootctl production data boundaries. Keep WebView historic BLOCKED and require supported WebUI acceptance or formal scope retirement at release; never convert blocked cases into success.


## Skybind B0+B1 adoption — verified 2026-10-16

### SB-DEV-B01-001 — Legacy Android probe target conflicts with GitHub-only APK policy
- **Status:** Remediated in proposed Skybind B0+B1 overlay, native-host and CI requalification pending.
- **Affected:** `skybind_app_probe` AndroidGradleRunner, `build-app-probe`, `app-probe`, `install-app-probe`; new `skybind_android_app` target.
- **Evidence:** The archived Skybind config had `runner="android"`, `:app:assembleDebug`, and workflows invoking `runner:android#build` locally. New source policy would have been incomplete without retiring it.
- **Change:** Fail-closed legacy Q10 entrypoints, preserve original test source in history, use hosted Actions only. Static policy tests pass. Do not re-enable local Gradle even for instrumentation APKs.

### SB-DEV-B01-002 — Consumer `.go` fixture files polluted Go package discovery
- **Status:** Fixed and verified in 4-stage Devtool R1 source invocation.
- **Affected:** `tests/fixtures/r0-consumers/{bkx,chroot}/...` and GoRunner `test ./...`.
- **Evidence:** First actual Devtool `r1-source` execution failed importing `bkx/internal/...` and `chrootctl/internal/...` as if in Skybind Go module. Renaming archived exact bytes to `.go.fixture` preserves SHA-256 and excludes them from Go package discovery.
- **Change:** Source contract tests independently hash `.go.fixture` bytes; explicit `--audit-source` still verifies true consumer paths. Repeat `r1-source` PASS: four stages, 270 Go tests passed.

### SB-DEV-B01-003 — Android artifact byte checks do not authenticate hosted CI identity
- **Status:** In progress; source producer and local verifier implemented, authenticated remote verifier NOT IMPLEMENTED.
- **Affected:** Skybind Android CI artifacts, Devtool Actions dispatch/resume, independent installation receipts.
- **Evidence:** Manifest creation requires GitHub identity environment and stores exact APK digests and cert fingerprints; local verifier deliberately reports `github_run_authenticated=false`.
- **Next:** Verify job/run/attempt/workflow/ref/head SHA via GitHub API, archive identity and installed bytes; no qualification from a successful artifact upload alone.

### SB-DEV-B01-004 — Safe cross-target source DAG adopted
- **Status:** Implemented in B0+B1 Skybind source; Devtool invocation PASS.
- **Affected:** `skybind_release#r0-compat`, `#r1-source`, target-local jobs and native GoRunner.
- **Evidence:** Devtool planner resolved 3 R0 tasks and 4 R1 tasks. `invoke r1-source` PASS after fixture remediation, 4 stages, 0 warnings/errors, 270 Go tests PASS. This is an offline source verification gate, not APK/device/release qualification.

### SB-DEV-B01-005 — Physical device serialization metadata
- **Status:** Target metadata added; live multi-workflow lease verification pending.
- **Affected:** `skybind_android_device` physical app-probe, A1-B3 readonly/disposable, WebView/boot and interactive source jobs.
- **Evidence:** Previous scheduler had `max_android_device=1` but did not mark all local device operations as `device-exclusive`. B0 metadata adds shared reservation `skybind:physical-device` and removes `read_only=true` from receipt writers.
- **Next:** Check scheduler reservation behavior on native Termux using one actual phone before enabling physical device parallelism; separate ADB transports of the same phone are not independent devices.

### SB-DEV-B01-006 — Hosted Kotlin toolchain compatibility preflight
- **Status:** Source corrected, hosted build pending.
- **Evidence:** Initial native app scaffold used Kotlin Gradle plugin 2.0.21 with AGP 8.9.2 / Gradle 8.11.1, outside Kotlin's documented fully supported matrix. Verified Kotlin 2.2.21 supports AGP 8.9 and Gradle 8.11.1; corrected both Kotlin Android and Compose plugin pins and source guard.
- **Follow-up:** Actual compile from hosted GitHub Action, then digest/certificate proof. Never compile an APK locally to validate the fix.

## SB-B01-WAITDELAY-011 — Go test pipe WaitDelay on native Termux, independent source jobs skipped

- **Status:** Workflow dependency repair implemented and source-verified in the Skybind B01-W1 hotfix, **native Termux still pending**. Underlying Go process-I/O problem **open; root cause unknown**.
- **Affected:** Skybind `skybind_go#test` native GoRunner invoking `go test -json -p 2 ./...`; `skybind_release#r0-compat`, `#r1-source`; Devtool fail-fast scheduling/diagnostics. No general Devtool implementation defect demonstrated.
- **Observed evidence:** Native user execution `c569f0dab44a460e85d2a49b05fd8140` on 2026-10-17 UTC, 490.799 seconds, 27 Go packages passed, 4 failed (`mounts/lifecycle`, `mounts/policy`, `opevents`, `paths`), 2 no tests. Each failure: `exec: WaitDelay expired before I/O complete`; Go prints `*** Test I/O incomplete 1m0s after exiting.`. Three downstream source-contract nodes skipped because the broad Go package gate was an ancestor; Devtool correctly reported failure rather than assuming test PASS. `internal/paths` test source does not launch child processes, so a single Skybind subprocess leak is not proven.
- **Change:** Change `r0-compat` to BKX/chrootctl offline contracts only; change `r1-source` to independent R0 and R1 brokergrant contract nodes; introduce `r1-full-regression` composing that fast DAG **and unchanged full GoRunner**. Nothing from a fast PASS can satisfy full regression acceptance. Add source-bound private per-package Go diagnostic script with package whitelist, serial `-p 1`, no cache, bounded timeout, machine JSON and SHA-256 of logs. Keep failed historical run and release qualifications unchanged.
- **Local source evidence:** Devtool 2026-10-15 archived source planned `r1-source` as 3 focused nodes and `r1-full-regression` as 4 focused+full nodes; Devtool invoked fast source DAG PASS 3/3 stages in ~3.87s on Linux. Isolated Linux probes on `paths` and `mounts/policy` PASS, not a native-Termux qualification and do not rule out device-specific failures.
- **Next:** On native Termux use the B01-W1 diagnostic; distinguish reproducible isolated failure, concurrent-only failure, and GoRunner-only failure before changing process launch or Go toolchain settings. Preserve source exactness and do not bypass `r1-full-regression` when approving the B0/B1 milestone.

## SB-B01-WAITDELAY-012 — Termux full Go regression concurrency isolation

- **Status:** B01-W2 Devtool target policy implemented in separate Skybind overlay; configuration/source-contract verification performed on inspection host; **native Termux full gate pending**. Root cause of intermittent Go test pipe closure still unresolved.
- **Evidence:** Native Devtool run `26adffe087b341a6b25e8aa390f6873e` had all three R0/R1 source contract jobs PASS, 29 Go packages PASS, but `internal/mounts/lifecycle` and `internal/opevents` produced `exec: WaitDelay expired before I/O complete` with `-p 2`. Four source-bound individually executed `-count=1 -p 1` probes (`paths`, `mounts/policy`, `mounts/lifecycle`, `opevents`) all PASS on native `go1.27.1 android/arm64` with no WaitDelay, matching protected source `7a1c8168fbc82603ce999ecc21d9ba791ce10779`.
- **Affected:** Skybind `targets.skybind_go.go.max_workers`, GoRunner resource policy, output events, release full-regression DAG. Devtool native GoRunner derives `go test -json -p N ./...` via `resolve_build_policy(config,'go')` and retains structured `go-test-json` reporting.
- **Recommendation/change:** Set target-local `max_workers=1` to serialize Go package tests on the constrained phone, without changing other Devtool targets, avoiding a global max-workers override, and preserving GoRunner + mandatory full-regression gate. Add a TOML source test to enforce the policy. Only regard this as an experiment until a **native full-suite** pass without WaitDelay is observed. If serialized Devtool fails while raw `go test -p1` passes, investigate Devtool process environment/I/O handling; if both fail, investigate Go Android runtime or device resource pressure. Keep the original failed reports. No Android APK compilation locally.
- **Status of broader program:** GitHub Actions APK compilation and real cross-UID grant acceptance remain pending; source-policy tests do not release them.

## SB-B01-WAITDELAY-013 — `-p 1` insufficient; source-bound per-package regression workaround

- **Status:** W3 alternative implementation; host fully tested; **native Termux W3 pending**. Original WaitDelay cause open, no false positive classification permitted.
- **Evidence:** Native run `dcd6002c0bce486eb1a0864300cd95d0`, `2026-10-17T03:16:26Z`–`03:25:55Z`, exited 1 after 569.337s. BKX 9/9, chrootctl 5/5 and R1 policy passed. Devtool GoRunner correctly invoked `go test -json -p 1 ./...` but `internal/mounts/supervisor` failed `exec: WaitDelay expired before I/O complete` after starting `TestQ07BudgetPersistsAcrossPolicyDeferAndDaemonRestart`. The other 30 tested packages passed, with 2 packages having no tests. Former failure packages `lifecycle` and `opevents` passed this time. This disproves package serialization as a complete fix and suggests intermittent Go process I/O or device execution behavior, not a reproducible supervisor test assertion.
- **Implementation:** New Skybind Devtool target-local job `skybind_go.isolated-regression`; `go list -json ./...` discovers complete package population. Every listed package runs in its **own**, uncached, one-package `go test -json -count=1 -p 1` process with isolated output file and independent timeout; JSON parser requires matching package identity, valid complete package pass/skip events, no failing tests and no WaitDelay. Dirty Go tree source digest checked before/after, each log hashed, receipt persisted after each package. Any failure exits nonzero and blocks complete regression. Clears ambient `GOFLAGS`/workspace overlay to preserve exhaustive coverage. Existing native Devtool GoRunner maintained as independent `r1-go-runner-diagnostic` for root-cause investigation.
- **Host proof:** The new standalone runner on extracted source executed **33/33 Go packages** on `go1.23.2 linux/amd64`, including `lifecycle`, `supervisor`, `opevents`; each had exactly one valid terminal pass or no-test skip; all had zero WaitDelay. This proves the source run path, not Android resolution. An intentionally partial 2-package selection remained non-qualifying even when both passed. Native W3 must run before accepting the new full-regression gate. Devtool source workflow on Linux inspection host also PASS **4/4 stages** in 16.09s: 33/33 Go packages, 270 test PASS events, 2 no-test-file packages; hash-bound receipt `985629c06385870e4fd2842d9223da7ffaf61786d2f3159b08396aba3dcd9206`. New JSON negative controls verify missing, duplicate, failed, invalid, wrong-package and WaitDelay events cannot pass.
- **Follow-up:** Inspect native receipt; if package-independent failures continue, collect Android process pressure/logcat and compare raw single-package stdout vs redirected terminal. Go tool / process FD root cause remains unresolved. Do not promote B1 cross-UID or GitHub Actions APK builds from source-only evidence.


## B1A-OVERLAY-001 — Apply-time nested validation and isolated worktree mismatch

- **Status:** Open Devtool product issue; observed in archived 2026-10-15 source. Avoidance implemented in Skybind B1-A overlay; no Devtool source fix claimed.
- **Affected:** Devtool canonical artifact qualification, apply-time artifact tests/refs, isolated-worktree validation, workflow execution.
- **Evidence:** Native artifact schema-v2 overlay with `validation.required=true` and `validation.refs=["workflow:r1-transport-source"]` passed structural `check_overlay` but `apply-overlay --validate` was rejected by canonical preflight as `required-validation-unresolved` because the lifecycle contract looks at `validation.tests[].ref`, not `validation.refs`. Adding a `tests[].ref` passed preflight, but the initially selected Skybind `validate` workflow still pointed to obsolete bootstrap checks. After changing that default to the actual R1 source DAG, direct stage execution passed yet artifact validator failed from `.../worktree/release/internal/brokeripc: directory not found` and `cannot start terminal node ... with status succeeded` when re-entering the workflow.
- **Proposed Devtool changes:** Unify canonical validation refs from both `validation.refs` and `validation.tests`; resolve relative test cwd against repository root rather than selected sub-target root; make nested workflow replay/resume idempotent and avoid duplicate terminal node starts; add disposable CLI integration tests with a multi-target repo, strict validation, and Git transaction.
- **Skybind policy:** Native schema-v2 artifact manifest with SHA-256 per-path inventory, strict source-state conflict rejection, atomic apply, scoped commit; automatic apply-time validation remains **optional** in this overlay. Run its independent `r1-transport-source` Devtool workflow post-apply and the full W3 regression before milestone acceptance. Do not treat apply success as qualified evidence.

## B1A-OVERLAY-002 — `validation.mode=disabled` creates invalid CLI skip flags without validation

- **Status:** Open Devtool ergonomics bug; source/workflow avoidance documented.
- **Evidence:** Artifact with `validation.required=false, mode=disabled` was parsed into `--skip-restore`, `--skip-build`, `--skip-test` but then CLI rejected these flags because `--validate` was not active. A manifest containing only `validation.required=false`, with explicit `--no-validate` at smoke test, avoided the inconsistent flag synthesis.
- **Proposed:** Normalize disabled validation before generating skip flags; keep no-validation overlay application legal, and test direct vs wrapper CLI parity.

## B1A-TRANSPORT-003 — Read-only broker transport is source-qualified, not production-connected

- **Status:** R1 B1-A source implementation validated on Linux; native Termux and Android cross-UID acceptance pending.
- **Affected:** `internal/brokeripc`, `internal/brokergrant`, `skybind_api_contracts` Devtool target, `skybind_release#r1-transport-source` DAG, Android hosted-build source policy.
- **Evidence:** 2026-10-17 archived-source implementation, 5 stage Devtool DAG PASS on Linux. Schema-v2 Devtool overlay `SKYBIND_B1A_BROKER_TRANSPORT_DEVTOOL_OVERLAY_20261017.zip` passed inventory check, transaction apply, scoped Git commit, and post-apply DAG smoke in disposable repository. Only those five touched paths were committed. Native W3 full Go isolated regression PASS was reported by the user; no accompanying W3 receipt was provided in this turn. Historical monolithic Go WaitDelay remains open and is not rewritten.
- **Follow-up:** Implement kernel PID/UID + Android signing/package/PID start identity verifier and explicit grant control plane; integrate bounded read-only broker into daemon behind an opt-in switch; run hosted-only app and test APK builds followed by on-device process-auth tests. No local Android APK compilation.

## SKYBIND-B1B-IDENTITY-001 — Android caller attestation remains platform-bound
- **Status:** Source contract and negative tests implemented 2026-10-17; live platform authority PENDING.
- **Affected:** Skybind `internal/brokeridentity`, `internal/brokeripc`, Kotlin `UidPackageEvidence`, B1 unified roadmap.
- **Evidence:** B1-A transported `SO_PEERCRED` but trusted Android package certificate checking was not implemented. B1-B now binds `/proc/PID/stat` start ticks + kernel UID + strict `status` UID evidence, and mandates a trusted `PackageAttestor`; all unset/invalid cases fail closed. Kotlin PackageManager helper can locally verify a pinned signing SHA-256 but **cannot be relied on as an untrusted RPC attestation**.
- **Recommendation:** Provision a trusted Binder/Android package manager authority with authenticated IPC back to the Go broker, seal chrootctl's root module separately, test exact APK signing/installed package/UID and SELinux interactions on the physical phone. Never promote synthetic tests as device qualification.

## SKYBIND-B1B-ISSUE-002 — Explicit issuance workflow needed before real cross-app access
- **Status:** Internal grant issuer implemented and unit-tested, production trust path NOT_CONNECTED.
- **Affected:** Skybind `internal/brokerissue`, `internal/brokergrant`, R1 Devtool source workflow.
- **Evidence:** New issuer requires an exact operator-approved rule, verified process incarnation, fixed remote and prefix, read-only operation set and bounded TTL; it rechecks peer identity immediately before minting and preserves revoke/expiry. There is no untrusted remote issuer endpoint.
- **Recommendation:** Wire operator consent and trusted on-device evidence; add release-grade negative tests for UID-sharing, forged process identity, certificate rotation, PID reuse, missing permissions and boot recovery.

## SKYBIND-B1B-TEST-003 — Early deny races with client write
- **Status:** Source test reliability repaired for B1-A broker fixture; 3 focused repeated suites passed on Linux.
- **Affected:** `internal/brokeripc/server_test.go`.
- **Evidence:** When a verifier denies immediately, `ServeConn` can legitimately send denial and close before the synthetic client finishes writing; a `broken pipe` on the client should not fail a test whose intended assertion is denial. The test now tolerates EPIPE while still requiring the server to return a denied response and report an error.
- **Recommendation:** Preserve denial/negative assertions, add device socket lifecycle coverage; do not suppress unexpected parser or successful-response errors.

## SKYBIND-B1B-REMOTE-004 — Public GitHub repository lookup mismatch
- **Status:** OPEN / requires source identity resolution; no remote change attempted.
- **Affected:** Skybind remote source checking, Actions dispatch and artifact provenance.
- **Evidence:** Source archive Git origin is `git@github.com:Mikeyphw/skybind.git`; both connected GitHub and public repository search returned no accessible repository at this path on 2026-10-17. Source SHA remains the offline archive's `7a1c8168...` baseline, not the user-reported newest commit.
- **Recommendation:** Confirm actual accessible repository URL and source SHA on the user's Termux before Actions dispatch or remote qualification. Never mark GitHub build as complete based on a local ZIP.

## SB-B1B-OVERLAY-001 — Incorrect combined B1A/B1B source baseline (2026-10-17)

- **Status:** Resolved in corrected B1-B-only overlay; native application pending.
- **Affected projects:** Skybind (`.devtool.toml`, `internal/brokeripc`), Devtool overlay publisher.
- **Evidence:** `skybind-20261017-023429-863590.tar.gz` already contains B1-A, SHA-256 `.devtool.toml` `249a755344aa777d7fc81b83a4d56734c0a2c9369d06360748f6a951ac0285e3`. Combined B1AB overlay expected pre-B1-A `399e112b36320cfe4c2c5dbb620b3a0541fe3afc05470893bc83ed03f77278c8` and marked existing broker IPC files `add`. This properly triggers source mismatch/conflict.
- **Resolution:** Emit a delta overlay against the actual recipient snapshot: `modify` for existing files with current `source_sha256`, `add` only for absent files; omit unchanged B1-A files; test native Devtool check/apply on a disposable Git repo and source DAG. Never use `--force`, overwriting, or bypassing checksum checks to paper over baseline drift.
- **Next:** Verify application against actual Termux worktree SHA; B1-B sources are not production identity attestation.


## 2026-10-17 — Skybind ↔ Devtool source adoption review (`5cfcd3c` / `b45ce65`)

This addendum is based on inspected and locally executable source from both uploaded snapshots, not on remotely qualified code or Termux device execution. Full observations, recommendations, and commands are in `SKYBIND_DEVTOOL_SOURCE_STUDY_20261017.md`.

### SKY-EXO-WRITE-001 — Go regression incorrectly marked read-only
- **Status:** CONFIRMED source-policy defect; repair NOT applied.
- **Affected:** Skybind `.devtool.toml` / `skybind_go.jobs.isolated-regression`; Devtool `workflow_scheduler.py`.
- **Evidence:** `read_only=true` despite declared `build/evidence/go-regression-isolated/**` outputs; `scripts/dev/diagnostics/go_all_packages.py` creates per-package logs and summary under that location.
- **Action:** Remove false `read_only`; keep explicit output scope; add source-contract regression. Audit other receipt producers before enabling concurrency.

### SKY-R1-TEST-002 — Stale full-regression dependency test
- **Status:** REPRODUCED; repair NOT applied.
- **Affected:** `tests/test_r1_go_runner_policy.py` in Skybind.
- **Evidence:** 2026-10-17 `python3 -m unittest tests.test_r1_go_runner_policy tests.test_b1b_devtool_contract -v` gave 7/8 passing; expected R1 transport while actual, intentionally updated B1-B dependency is R1 identity.
- **Action:** Update only the expected dependency and retain Go isolated acceptance.

### SKY-EXO-SCHED-003 — Safe parallel source workflows
- **Status:** Planner experiment only; no native speedup qualification and no repo change.
- **Evidence:** Actual archived Devtool planner: R1 source full-regression 8 waves sequential, 3 waves with unconstrained opt-in parallel, 4 waves with corrected Go evidence write flag and a shared `skybind-go-build-cache` global reservation across four Go jobs.
- **Action:** Leave scheduler parallel off by default pending native pressure and receipt parity test; pilot bounded opt-in after P0 repairs. Maintain physical-device exclusive lanes.

### SKY-R1-DUP-004 — Duplicated Go-package invocations
- **Status:** Source-confirmed; optimization deferred until instrumentation and coverage proof.
- **Affected:** Skybind R1 policy/transport/identity jobs and uncached full Go regression.
- **Evidence:** `brokergrant` and `brokeripc` recur across independent targeted `go test -count=1` jobs before the full suite tests all packages again.
- **Action:** Separate fast feedback and full-regression acceptance; prove coverage unchanged, then deduplicate only unnecessary runs.

### SKY-ACTIONS-005 — Authenticated hosted APK adoption pipeline
- **Status:** Missing integration; remote identity unresolved, no CI claimed.
- **Affected:** Skybind hosted `skybind-android-apks.yml`, Devtool `actions_pipeline.py` / ACTIONS-02..06, Android manifest and device gates.
- **Evidence:** Hosted workflow publishes manifest and app/test APK ZIP, but local manifest verification correctly has `github_run_authenticated=false`; no source-bound pipeline + remote attempt/authentication + device acceptance receipt is wired. GitHub repository access returned 404 in this assistant environment.
- **Action:** Add canonical Actions-06 tracked pipeline and independent APK-byte/signature/installation checks. Explicitly preserve WAITING_REMOTE, uncertain POST, debug-unqualified and APK-local-build-prohibition boundaries.

### SKY-EXO-WRAPPER-006 — Wrapper and EXO adoption ergonomics
- **Status:** Enhancement proposed; not implemented.
- **Affected:** 70 Skybind wrapper commands / 87 target-local jobs / 11 targets; EXO summaries and operator workflow.
- **Evidence:** Existing wrappers are canonical (`wrapper exec`) but lack consolidated B1 host/device acceptance overview; Go isolated receipt and EXO events have separate source identifiers.
- **Action:** Keep canonical wrapper/DAG interfaces, expose appropriate source-only and remote/device phases, correlate EXO run identity and Go receipt hash, and verify via `wrapper seal`, `target-local-jobs --json` and `plan/preflight --json`.


## 2026-10-17 — Skybind B1-QW1 scheduler repair overlay (`b45ce65`)

**Status:** IMPLEMENTED IN DISTRIBUTED SOURCE-BOUND OVERLAY; test-applied and committed in a disposable Git checkout; **not applied to the user's Termux worktree**, with no native device or GitHub qualification.

- `SKY-EXO-WRITE-001`: resolved in B1-QW1 artifact: isolated Go job declares `read_only=false`; preserves `build/evidence/go-regression-isolated/**` and test assertion.
- `SKY-R1-TEST-002`: resolved in B1-QW1 artifact: stale R1 transport expectation corrected to B1-B identity-source dependency, retaining nested transport/cloud checks.
- `SKY-EXO-SCHED-003`: shared `skybind-go-build-cache` reservation added to four Go-testing jobs. Devtool source-bound planner produces 8 default sequential waves and 4 bounded opt-in parallel waves, from 8 nodes. Native Termux timing/pressure qualification is still **pending**, so parallel remains disabled globally.

**Validation evidence:** Devtool schema-v2 `validate-overlay` PASS; complete `apply-overlay` with embedded validator and single commit PASS in a disposable repo; 11 targeted unit tests PASS; clean fixture after Devtool commit; deliberate drift on `.devtool.toml` rejected by `source_sha256` mismatch. No local Android Gradle build or device mutation performed.

**Follow-up:** User should apply the distributed artifact to the exact baseline in `$HOME/Code/skybind` through Devtool without bypass flags. Stop on checksum/conflict failure, reconcile the actual source first. Compare EXO Go runtimes on Termux before opting into concurrent workflows. Preserve all historical acceptance receipts.


## 2026-10-17 — Skybind B1-QW2 Termux scheduler A/B witness

**Status:** Implemented as a source-bound Devtool overlay and successfully applied to a disposable Git copy; **user Termux execution pending**. User explicitly confirmed QW1 was applied before requesting the next implementation. All older QW1 statements above remain the historical release-time observations.

- **SKY-EXO-SCHED-003:** B1-QW2 adds a conservative Devtool-targeted `plan` wrapper, explicit baseline/candidate `invoke` stages, retained raw and EXO machine receipts, and exact Go package/log/source identity reconciliation. Tested planner: 8 sequential versus 4 bounded opt-in waves, Go jobs serialized. **No actual Termux performance gain yet claimed.** Default scheduler remains sequential; no involuntary extra tests.
- **SKY-EXO-WRAPPER-006:** A new first-class `skybind_release#r1-scheduler-plan` target-local job and `r1-scheduler-plan` wrapper command use the canonical Devtool resolver. No duplicate scheduler or custom APK CI implementation.
- **SKY-EXO-PROVENANCE-007:** Stage receipts bind Git commit, config hash, Devtool machine payload hash and log, Go per-package evidence summary SHA, package identities, and Go source digest. Tampered/partial/skipped/WaitDelay evidence fails closed; comparison cannot promote device/release qualification.
- **SKY-R1-DUP-004:** Historical full-Go suite remains mandatory for each A/B leg. Do not deduplicate until independent coverage and native-host measurements support it. Ongoing cost is explicit, not hidden.
- **Remaining:** Run staged A/B with controlled Termux resource profile; review duration/Go WaitDelay. Then implement `SKY-ACTIONS-005`: tracked authenticated GitHub Actions APK pipeline and source/run/artifact provenance (GitHub repository access remains unresolved in assistant environment). Device bridge B1-C follows separately.

**Validated:** 17 targeted unit tests; native Devtool source-bound validate/apply/commit in disposable checkout, `./devtoolw r1-scheduler-plan` and direct planner; deliberate SHA drift rejection. No Termux native workload or hosted/device acceptance executed.

---

## 2026-10-17 — Skybind B1-QW3 hosted APK pipeline findings (additional)

### SKY-ACTIONS-005 — Native GitHub APK pipeline adoption
- **Evidence:** Skybind's hosted workflow produces the two APKs and a manifest, but previously lacked a single source/run/artifact-bound Devtool Actions-06 graph. `docs/devtool/r1_android_hosted_pipeline.json` supplies a 5-node source/policy/dispatch/result/archive DAG using the native Actions-06/04 engine.
- **Affected:** Skybind, Devtool Actions-06, authenticated GitHub APK receipt handling.
- **Resolution:** **IMPLEMENTED_IN_QW3_SOURCE; awaiting remote qualification.** Explicit authorization and source-matched `main` required; no GitHub remote run claimed.

### SKY-ACTIONS-COLLECT-008 — ACTIONS-05 workflow name hard-coded
- **Evidence:** Devtool `devtool/actions_android.py::_WORKFLOW` is `devtool-android-build.yml`. `android_collect()` compares remote workflow ID against this name, disallowing Skybind's `skybind-android-apks.yml`, even when a native ACTIONS-06 run/archive is valid.
- **Affected:** Skybind hosted pair collection and all third-party projects with custom Android workflow names.
- **Recommendation:** Add documented `--workflow` to Android inspection/collection, pin workflow ID, source/ref/run attempt/artifact and trust source against remote GitHub API; preserve negative cases and no release-qualification inference. Avoid copying GitHub API scheduler.
- **Status:** **OPEN_DEVTOOL_UPSTREAM**. Skybind QW3 implements a narrow source-pinned bridge that uses ACTIONS-04 and shared Devtool APK inspection until Devtool supports arbitrary workflows.

### SKY-ACTIONS-PAIR-009 — Paired debug APK provenance and signing consistency
- **Evidence:** Current workflow emits an app/test APK and its self-generated source/run manifest; a ZIP hash alone cannot verify package IDs, two signatures, or current GitHub execution. The bundled `apk_manifest.py verify` explicitly says `github_run_authenticated=false` in local-only results.
- **Affected:** Skybind app, Skybind instrumented UI APK, future B1-C trusted-package authority and device testing.
- **Resolution:** **IMPLEMENTED_IN_QW3_SOURCE; awaiting real runner/SDK evidence.** The verifier requires native Actions-04 live verification and registry attempt, compares ZIP and manifest bytes to source/run/attempt, then invokes Devtool's APK inspector for each. Fail-closed if `apksigner`, `aapt`, or `aapt2` missing. Never call it device/release qualified.

### SKY-ACTIONS-DISPATCH-010 — Uncorrelated 204 dispatch is not a verified run
- **Evidence:** Devtool `github_actions.py::dispatch` records GitHub HTTP 204 as `accepted-uncorrelated` with no run ID; `actions_pipeline.py` marks a dispatch without run ID `uncertain` and refuses to redispatch. This protects against unrelated-run misattribution.
- **Affected:** ACTIONS-06 pipeline UX and Skybind hosted APK acceptance.
- **Recommendation:** Add an explicitly authorized, source/workflow/attempt-verified operator reconciliation path for uncertain dispatches; never silently infer a matching run from timing.
- **Status:** **OPEN_DEVTOOL_UPSTREAM**; QW3 documentation preserves fail-closed behavior rather than introducing unsafe retry logic.


## 2026-10-17 — Skybind QW3 H1 hosted SDK installation failure (run 39049326402)

### SKY-ACTIONS-SDK-011 — Multiline `setup-android@v4` package input forwarded as a single invalid SDK path
- **Status:** Fix implemented and qualified locally; new GitHub run pending.
- **Evidence:** GitHub Actions job `android-debug-apks`, step `Install hosted Android SDK build tools` failed before Gradle when `sdkmanager` searched for one package containing newline-separated `platforms;android-35`, `build-tools;35.0.0`, and `platform-tools`. Accepted SDK licenses succeeded. Devtool pipeline `a70ab1d83dab4a69a6e4d6c1ac4c4f95`; GitHub run 39049326402; source SHA `f8d38afd1b6b9d100c3da9375ff3551668c31af2`.
- **Affected projects:** Skybind hosted Android APK pipeline; Devtool source-only policy for third-party Actions configuration.
- **Remediation:** Replace YAML block with one quoted, space-delimited `packages` scalar and add a source-only guard and negative test against recurrence; optionally suppress accepted license agreement text output without changing acceptance.
- **Validation:** Devtool schema-v2 overlay validation PASS; full atomic apply/commit PASS (7/7) in disposable post-QW3 Git checkout; 37/37 contract tests PASS; intentional workflow source drift rejected before patch. Real remote requalification pending.
- **Devtool improvement candidate:** Provide a reusable target-local YAML/GitHub Actions workflow-lint contract for action inputs that are intended as whitespace-delimited single scalars; this would prevent pre-build hosted failures. Do not weaken native pipeline run/source or provenance requirements.


## 2026-10-17 — Skybind QW3-H2: machine-independent APK certificate verification

- **Issue:** The hosted APK manifest producer hard-coded `Signer #1 certificate SHA-256 digest:` as its sole accepted `apksigner verify --print-certs` output shape. The October 17 hosted run from source `b35cc0d2313b96e4546cba190e38de483dc16a75` built both APKs (`BUILD SUCCESSFUL in 2m 18s`; 66 tasks), then returned `FAIL_CLOSED: APK certificate fingerprint unavailable`; the certificate stdout was not in the failed-job log.
- **Affected:** Skybind `scripts/dev/android/apk_manifest.py`, `tests/test_android_cloud_policy.py`, GitHub Actions `skybind-android-apks.yml` manifest producer; downstream Devtool Actions-06 archive adoption was correctly blocked. Broader Devtool ecosystem impact: any source-bound hosted APK flow that parses human-readable apksigner signer labels instead of certificate material.
- **Root-cause confidence:** Format-sensitive parser is confirmed from source. A specific SDK-range label in the real runner output is plausible and documented in AOSP, but not directly observed; avoid claiming it as proven.
- **Recommendation:** Require successful `apksigner verify --print-certs-pem`, compute SHA-256 over the sole DER X.509 signing certificate, reject ambiguous or missing PEM, enforce app/test signer equality, and keep source/run/attempt/identity attestation unchanged. Retain negative tests and prohibit silent hash-only CI success.
- **Implementation:** `SKYBIND_B1_QW3_H2_SIGNER_PEM_SOURCE_BOUND_OVERLAY_20261017.zip`; two modified source files, one new doc; native schema-v2 atomic Devtool artifact. 46 source tests run (44 pass, 2 skip), 7/7 native apply stages passed in disposable checkout; source-drift negative passed. No actual GitHub run or device test executed for this revision.
- **Status:** `SOURCE_PATCH_VALIDATED_AWAITING_REAL_HOSTED_CERT_RECEIPT`. Preserve failed GitHub runs and previously qualified source-bound evidence; a new workflow/run/commit is required.


## 2026-10-17 — B1-QW3 H2 hosted pair collected; Termux APK metadata inspector blocked

### SKY-ACTIONS-APK-META-012 — Fragile `aapt[2] dump badging` parser
- **Status:** OPEN — needs local tool output to select minimal, source-bound remediation. No GitHub rebuild authorized or needed yet.
- **Evidence:** User confirmed all five Devtool Actions-06 nodes success for pipeline `be9ee025156643fe9a5c21d577dd0d2f` and GitHub run `39070051696` at source `1b808119720ed3c042ffc2a8fa84ebe313697eb8`. The independent attestor returned `FAILED_OR_BLOCKED` / `APK package metadata could not be verified`. Inspection of Devtool snapshot `devtool/actions_android.py::_inspect_apk` shows successful `apksigner verify --print-certs` and `aapt` (or fallback `aapt2`) `dump badging` are followed by a hard-coded ordered regex `^package: name='...' versionCode='...' versionName='...'`. That error is raised only when this format fails to match or the extracted package identifier fails validation. Actual Termux tool binary/output has not been captured.
- **Affected:** Devtool native ACTIONS-05 shared APK package inspector; Skybind `r1_hosted_apk_attest.py` paired APK acceptance; possibly Termux aapt/aapt2 output compatibility and other client projects.
- **Next evidence:** Read-only package-line capture from the exact source/run-bound authenticated archive using the *same selected binary* as Devtool, for both `app-debug.apk` and `app-debug-androidTest.apk`. Capture the tool path, exit status, package line, and regex match; do not upload full APKs, installed apps, private keys, or secret manifests.
- **Recommendation:** Fix upstream Devtool to parse package ID and version attributes robustly from authoritative tool output, enforce a single unambiguous package identity, continue required signature verification and exact signer-hash comparison; add regression cases reflecting real Termux output. A source-bound Skybind workaround should be explicit and tested only if upstream fix cannot be deployed first.
- **Qualification impact:** Hosted Android APK build and Actions-06 archive collection remain successful; local package inspection failed closed; no Android device or release qualification is established. Do not rerun the hosted build just to debug local parsing.


## 2026-10-17 — Skybind QW3-H3: confirmed Gradle androidTest APK empty version attributes

### SKY-ACTIONS-APK-META-012 — Native Devtool APK version parser rejects valid instrumentation variant
- **Status:** ROOT_CAUSE_CONFIRMED; temporary, narrow read-only runtime adapter TESTED_LOCALLY; permanent native Devtool remediation OPEN.
- **Real Termux evidence:** `aapt dump badging` returns `package: name='io.github.mikeyphw.skybind' versionCode='1' versionName='0.1.0-dev'` for the app; the instrumentation APK line is `package: name='io.github.mikeyphw.skybind.test' versionCode='' versionName=''`. Native Devtool `_inspect_apk` uses `versionCode='([^']+)'`, which rejects the empty test-APK field before the archive is accepted; `versionName='([^']*)'` already permits blank names. The tool executes successfully and the package name is syntactically valid.
- **Authenticated upstream state:** Native Actions-06 five nodes passed for `be9ee025156643fe9a5c21d577dd0d2f`, source `1b808119720ed3c042ffc2a8fa84ebe313697eb8`, run `39070051696`. The separate QW3 attestor failed closed only during local package inspection. Do not rewrite source/dispatch for this local compatibility issue; the original pipeline remains valid.
- **Immediate workaround:** `attest_h3_compat.py` temporarily replaces native Devtool's in-memory `_inspect_apk` only after the exact metadata error. Allows *only* the `.test` package with two explicitly empty version fields and exactly one `instrumentation:` badging line whose `targetPackage` names the app. Independently reruns `apksigner verify --print-certs`, `aapt dump badging` and the native fingerprint extractor. The unmodified `inspect_android_zip` retains APK SHA-256 extraction, expected package, expected certificate, member verification and the original source/run/attempt/registry/ZIP witness. The adapter is stored outside the source tree and does not mutate Devtool packages or Git. Twelve mocked positive and negative tests passed. No on-device execution, build or release qualification claimed.
- **Permanent Devtool improvement recommendation:** extend `devtool/actions_android.py::_inspect_apk` and `inspect_android_zip` with an explicit `apk_role=application|instrumentation` or equivalent trusted context. Permit empty version code only for known test APKs under a pinned test/application relationship, continue strict positive numeric `versionCode` for normal application/release packages, require exact instrumentation `targetPackage`, single package declaration and verified signing identity. Unit and live Termux regression tests must prove negatives. Avoid fake version strings, global regex changes, or blanket weakening. Update native Actions collection to accept caller-approved workflow identity separately (`SKY-ACTIONS-COLLECT-008`).
- **Affected projects:** Devtool shared Android APK inspector, Skybind source-bound hosted APK acceptance, other Android instrumentation APK consumers.
- **Validation boundary:** Tested the adapter's decision logic locally; actual Termux APK inspection remains user-run. Do not infer device/release qualified until explicit acceptance.


## 2026-10-17 — Skybind QW3-H4: instrumentation declaration format correction

### SKY-ACTIONS-APK-META-013 — Instrumentation target inspection from unsupported `badging` representation
- **Status:** H3 runtime adapter FAILED real Termux inspection; H4 replacement passes local regression tests, real Termux validation PENDING. Permanent Devtool core fix OPEN.
- **Evidence:** User ran `SKYBIND_B1_QW3_H3_LOCAL_ATTEST_COMPAT_20261017.zip` against completed pipeline `be9ee025156643fe9a5c21d577dd0d2f`; result `FAILED_OR_BLOCKED` / `Instrumentation target declaration missing or ambiguous`. H3 source searches for `instrumentation:` in `aapt dump badging`. AWS Device Farm Android instrumentation troubleshooting explicitly requires `aapt dump xmltree <APK> AndroidManifest.xml` and inspects its `E: instrumentation` and `A: android:targetPackage` lines. The H3 output does not prove that the target declaration is actually absent.
- **Affected:** Temporary Skybind QW3-H3 adapter, Devtool shared APK metadata inspector, Termux aapt/aapt2, other projects with androidTest APKs.
- **Correction:** QW3-H4 one-shot local adapter uses `aapt dump xmltree` / `aapt2 dump xmltree --file`, verifies manifest package `io.github.mikeyphw.skybind.test`, single instrumentation element, `androidx.test.runner.AndroidJUnitRunner` and target `io.github.mikeyphw.skybind`. Preserves exact source/run/attempt/archive/signature checks; does not modify tracked repository or dispatch another build.
- **Verification:** 20 mock-based tests passed, including output absent from badging, aapt2 alternative, bad/wrong/duplicate attributes and negative signature cases; zip file SHA-256 verified. No production Termux APK metadata output captured at H4 stage; no claim of final attestation or device acceptance.
- **Recommendation:** Add role-aware `application|instrumentation` APK inspection in Devtool; treat test APK versions independently, parse compiled manifest `instrumentation` for target, and retain strict digest/signature binding. Add integration fixture with actual Termux `aapt` outputs and fail-closed negative cases.


## SKY-B1C-DEVICE-013 — Source-bound installed APK byte provenance and Android identity acceptance

- **Status:** B1-C1 device harness implemented locally, source-only tests PASS; **native Android execution pending**. No APK rebuilt, replaced, or installed by the overlay.
- **Affected:** Skybind `scripts/dev/android/r1_b1c_device.py`, Devtool `skybind_android_device` local jobs/wrappers, `build/evidence/android/b1c/`, Devtool APK adoption acceptance.
- **Evidence:** Hosted ACTIONS-06 pipeline `be9ee025156643fe9a5c21d577dd0d2f`, source `1b808119720ed3c042ffc2a8fa84ebe313697eb8`, run `39070051696`, H4 result `PASS_HOSTED_PAIR_INSPECTED_NOT_DEVICE_QUALIFIED`. Prior Devtool native inspector rejected empty instrumentation-version metadata; H4 local workaround verified Android XML target. Physical device package/certificate provenance and instrumentation remain separately unqualified.
- **Improvement:** Native Devtool should provide a first-class, artifact-bound device-adoption gate with unique ADB transport selection, installed APK byte/hash or platform signing-identity proof, proper app vs instrumentation roles, explicit install consent, two-APK atomicity or guaranteed safe compensation, privacy-safe immutable receipts, and separate live PackageManager/Binder trust. Source revision for the device harness **must not alter the original hosted source SHA in the APK evidence**; record harness revision independently.
- **Safety/negative:** No automatic replacement, uninstall, data clear, reboot, `su`, production broker enablement or cross-UID grants. Missing device, missing pulls, split installation, mismatch, ambiguous ADB transport, and failed/incomplete instrumentation remain blocked. `--install-missing` is explicit, only when both are absent; partial failures are disclosed and never silently rolled back. Two UI/security helper tests do **not** establish privileged Go broker identity or formal device qualification.
- **Follow-up:** Run native Termux source gate, read-only B1-C provenance, optional approved first install, scoped two-test instrumentation; preserve JSON. Implement separately trusted Android privileged attestation and real cross-UID negative tests before claiming full B1-C.


## 2026-10-17 — B1-C2 Android PackageManager not-found exit status

### SKY-B1C-PM-014 — `pm path` reports absent package via exit code 1, mistaken for PM failure
- **Status:** B1-C2 source-bound remediation implemented, offline negative tests PASS; real Android 16 recheck PENDING. Existing B1-C1 blocked receipt remains historical truth.
- **Evidence:** User-supplied B1-C1 preflight on arm64-v8a / API 36 reported `hosted_attestation=PASS`, `hosted_apk_bytes=PASS`, `installation_performed=false`, `state=BLOCKED`, `reason=PACKAGE_MANAGER_QUERY_FAILED`, attested pipeline `be9ee025156643fe9a5c21d577dd0d2f` and GitHub run 39070051696. The reviewed B1-C1 script `installed_apk` rejected `code != 0` from `adb shell pm path PACKAGE`. AOSP `PackageManagerShellCommand.displayPackageFilePath` returns 1 with no path for missing package. Actual ADB stdout/stderr for this device were not captured, so the precise on-device trigger remains to be confirmed.
- **Affected projects:** Skybind B1-C device harness and Devtool future shared Android device adoption/preflight utility; Termux and Android 16 shell package inventory; possible other consumers of `adb shell pm path`.
- **Root-cause remediation:** Accept *candidate* not-found only on `pm path` exit 1 with entirely empty output, then require successful independent exact package listing (`pm list packages --user 0 PACKAGE` without `-u`) to prove absence. Reject service/permission errors, malformed/duplicated entries, package-path/list contradictions, partial installs, and mismatching installed APK bytes. Preserve original authenticated APK source, archive, pair digests, AndroidJUnitRunner tests, and opt-in installation safety.
- **Validation:** 23 source/offline test cases incl. negative controls; native source-bound overlay validation/apply separately recorded in implementation report. Does not claim real-device, trusted cross-UID, or release qualification.
- **Devtool improvement:** Add an Android `pm path` role-aware classifier in native device-acceptance services that distinguishes confirmed absence from PM query exceptions and includes privacy-safe command/return-code evidence. Couple package-list fallback to the same explicit Android user and recorded ADB transport; fail closed on inconsistencies. Keep historical blocked states immutable.
