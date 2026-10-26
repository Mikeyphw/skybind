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


## SKY-B1C3-001 — UID observation is not a trusted broker identity oracle (2026-10-18)

- **Status:** Read-only device survey implemented, offline tested; on-device result pending. Authenticated cross-UID broker resolver NOT_IMPLEMENTED.
- **Evidence:** User-reported `PASS_B1C_DEVICE_INSTRUMENTATION` for hosted pipeline `be9ee025156643fe9a5c21d577dd0d2f`, with `ScaffoldTest` and `UidPackageEvidenceTest` passing and installed pair matching. Android app currently contains only local `UidPackageEvidence.verify()`, while Go `brokeridentity.AndroidVerifier` depends upon the as-yet unwired OS-trusted `PackageAttestor`.
- **Affected:** Skybind Android source, B1-C device harness, Go brokeridentity/brokeripc, Devtool Android device target, future BKX/chrootctl API consumers.
- **Change:** Add source-bound B1-C3 read-only survey that checks both PackageManager-facing CLI enumerations for unique package-to-UID ownership, SELinux enforcement, and immutable hosted APK hashes. Add testable positive and fail-closed negative parsing cases.
- **Recommendation:** Implement a trusted Binder service / authenticated platform identity channel with independent, cert-pinned package verification and OS-derived calling UID; integrate it with kernel peer credentials and PID-start binding. Never promote shell observations or app RPC payloads into privileged broker authorization; test negative cases on actual Android before opening external connections.
- **Qualification:** Survey success will be `PASS_B1C3_UID_OBSERVATION_NOT_BROKER_AUTH`, not release/device-broker qualification. Legacy and historical receipts retained.


## 2026-10-18 B1-C4–C7 consolidated security campaign

**Evidence:** User-reported `PASS_B1C3_UID_OBSERVATION_NOT_BROKER_AUTH` follows a passing B1-C1 installed-pair instrumentation receipt. The Go peer verifier still expects an OS-trusted `PackageAttestor`, and the Android app had no Binder-derived caller authority. The Go JSON decoder accepted duplicate scalar field names; the backend was reached after only two peer checks (before and after parsing).

**Implemented:** `BinderCallerGate.kt` (non-exported staging policy, OS transaction UID, locally provisioned pin, default-deny); Android instrumentation positive/negative signer cases; Go strict duplicate-key rejection and third post-grant pre-read identity check; successor new-source APK gate; one grouped Devtool command; immutable source/device evidence; security docs.

**Affected projects:** Skybind Android (including future BKX and chrootctl API consumers), Skybind Go broker, Devtool Android hosted/device qualification.

**Devtool improvements identified:** distinct app/test APK metadata policy (H3/H4 workaround must become native), source-bound multi-generation Android qualification without overwriting historical immutable evidence, declarative operator authorization for signer continuity or explicitly blocked reinstall, and shell-friendly workflow parameter passing of `pipeline_id` to target-local commands. Status: open for Devtool upstream; this overlay adds safe local wrappers but does not claim native fixes.

**Remaining:** Android Binder gate is not yet an authenticated privileged-Go package attestor; no external cross-UID physical device test fixture; no production listener/grants; new hosted build and device acceptance pending. These are security gates, **not deferred ordinary failures**.


## 2026-10-18 B1-C8 consolidated CI source regression remediation

- **Issue SKY-B1C8-001 — stale release denial:** GitHub source-validation run `39136103203`, commit `f525c4826844e7767aad07770d9d10ed3860c81b`, stopped at `test_no_release_without_device_or_upstream_pins`: test expected `NEWFUTURE_ARCHIVE_SHA256_UNPINNED` despite a syntactically valid SHA-256 in `scripts/dev/runtime/source.lock.json`. Corrected to require independent gates to remain blocked, while separately testing missing, malformed, and nonstring pins; a syntactically valid but unverified digest is explicitly **not** third-party authenticity proof.
- **Issue SKY-B1C8-002 — malformed lockfile shape:** `skybind_audit.blocked_report()` previously accessed `.get` on untrusted nested objects without validating mapping types, so JSON `null`/arrays could raise an exception. Explicit schema-type checks now return `PROVIDER_LOCK_UNTRUSTWORTHY`. Bclone toolchain pins must be nonempty strings. All audit outcomes preserve `BLOCKED`, `NOT_ISSUED`, and eight unqualified milestone gates.
- **Issue SKY-B1C8-003 — moved Go isolation authority:** `tests/security/test_c06_security.py` required a `GOTOOLCHAIN` token in `skybind_runtime.py` even though the reviewed source-build lane `source_build.py` now owns `GOTOOLCHAIN='local'` and pinned Go. The test checks its actual authority and continues checking the runtime packager and release guard.
- **Issue SKY-B1C8-004 — WebUI v9 QA inventory drift:** legacy WebUI parity fixture expected a finite list of added IDs but omitted 15 intentionally added read-only/disposable-only QA DOM IDs. Added exactly those IDs and asserted both QA modules are bundled. Unknown ID additions and missing reference controls still fail.
- **Issue SKY-B1C8-005 — Devtool product adoption drift:** bootstrap source contract was hardcoded to six original targets. It now recognizes five specifically adopted targets (Go, BKX, chrootctl, API and Android app), retains `bootstrap` on six original targets, checks valid workflow references for new targets, and rejects unknown additions.
- **Affected projects:** Skybind release audit/source CI, Go offline source builder, Skybind WebUI v9, Devtool target registry, future BKX/chrootctl API consumers. **Implementation:** one source-bound Devtool overlay with six modified source/test files, one new bootstrap regression file, and an appended cumulative improvements entry. **Qualification:** offline tests and source-contract checks only until fresh GitHub CI; never assert source success as release/device qualification. Historical APK evidence and physical-device receipts remain unchanged.
- **Long-term recommendations:** Prefer behavior-based source tests over exact historical string locations, distinguish pin formatting from authentic upstream verification, and maintain enumerated target and UI extension registries. Consider a faster mandatory source-denial preflight before full C06 Go race tests; do not weaken those full checks.
- **Status:** implemented locally in B1-C8 overlay; GitHub source workflow requalification and resulting source SHA remain pending until user applies/pushes overlay.


## SKY-B1C9-001 — Async job fixture teardown versus durable terminal persistence (2026-10-18)

- **Status:** Test-only source repair implemented and verified locally; native Devtool apply and hosted GitHub CI pending.
- **Evidence:** `Mikeyphw/skybind` GitHub Actions source-validation run `39142505777` on source `a5787d1c2098c86ea86bb73293d4cd78b7db94da` failed in `internal/daemon` at `TestB1RPCMountlessTransferBoundary`: `TempDir RemoveAll cleanup: unlinkat .../jobs: directory not empty`. The fake executor sent to a channel before its asynchronous Store worker persisted terminal state; the test returned and `t.TempDir()` removed the directory concurrently with a final `state.json` write.
- **Affected:** Skybind B1 remote transfer RPC and job-store test fixtures, GitHub source-validation workflow, grouped B1-C source checks, Devtool qualification reliability. No evidence of production remote transfer corruption from this test-only failure.
- **Change:** Register a buffered, nonblocking terminal lifecycle observer and a `t.Cleanup` barrier *after* `t.TempDir`, requiring the exact worker's `job.completed` event and verifying persisted `COMPLETED` state under the Store mutex. Bound the wait to five seconds and preserve failures for missing/incorrect terminal states; no arbitrary sleeps, skipped tests, altered production scheduler or weakened assertions. Add a 30-iteration Go reproduction gate to the grouped B1-C source workflow.
- **Validation:** 100 consecutive targeted normal Go test runs PASS, 30 targeted `-race` runs PASS, and `go test ./internal/daemon ./internal/jobs ./internal/brokeripc` PASS in the local source reconstruction. GitHub CI and device qualification not yet rerun.
- **Recommendation to Devtool:** Standardize source-bound background-worker fixture teardown checks and stress-gate evidence for job/daemon integration tests. Record CI flakiness separately from APK and physical-device status. Avoid automated GitHub redrive and no automatic device mutation.
- **Qualification:** Release remains `NOT_ISSUED`; historical hosted run `39136135918` and Android evidence remain valid for their own source SHA but must not be promoted to later commits.


## Native M1 UI resume — 2026-10-18

**Source-bound baseline:** `02aa0449fa0ba3d4985f4585906ce4d3a93e6f38` (B1-C9), with historical B1-C6 in-app Android device PASS. **Status:** implemented in proposed M1 overlay, local source/model tests PASS; GitHub build and on-device UI tests **PENDING**. This section must not be used as evidence that app-to-daemon authentication exists.

| ID | Finding / evidence | Recommendation / correction | Status |
|---|---|---|---|
| M1-APP-01 | `MainActivity.kt` was a single-page placeholder; offline views and M1/M2 screen semantics lacked instrumentation. | Native five-screen Compose navigation, typed snapshots, real UI semantic tags, UI/lifecycle test sources in GitHub-built separate test APK. | SOURCE IMPLEMENTED; DEVICE PENDING |
| M1-APP-02 | Product had no authenticated app/Go broker; in-process Binder test alone does not authorize external clients. | Keep production `UnpairedGateway` NOT_AUTHORIZED and unprivileged; implement trusted package-manager signing/UID verification and revocable read-only grant through vetted broker as a separate M1 gate. Do not enable root or copy credentials. | OPEN — BLOCKS LIVE HANDSHAKE |
| M1-APP-03 | Server-data separation needed: job queue and journal are different authorities; reconnect can otherwise expose stale data. | `SkybindReadSnapshot` distinguishes Jobs and sequence-keyed Activity, `failClosed()` scrubs stale remotes/mounts/jobs/events/cursor, historical Journal not a second job state. | SOURCE IMPLEMENTED; DEVICE PENDING |
| M1-APP-04 | Five-screen UI was not covered by navigation or lifecycle acceptance. | `NativeUiTest` fixture-only Compose semantics, negative/capability state checks; `NativeLifecycleTest` Activity recreation (not true process death); later external coordinator must prove force-stop continuity. | SOURCE IMPLEMENTED; DEVICE PENDING |
| M1-DEVTOOL-01 | Need one clear source lane without another matrix of wrapper commands; local APK builds prohibited. | Add M1 source gate as a grouped B1-C Devtool source step; preserve GitHub-only builds and source+artifact+device matching. | SOURCE IMPLEMENTED; CI PENDING |
| M1-DEVTOOL-02 | B1-C6 installed successor APK signatures may differ from newly built GitHub APKs; M1 overlay changes source commit. | New Actions-06 pipeline/attestation and explicitly authorized device install only after verifying signer/bytes; retain backup/history. Never conflate current source with old installed evidence. | OPEN — ACTION AFTER CI |
| M1-DEVTOOL-03 | Existing `current_source_sha` erroneously checks Git SHA-1 with `HEX64`; B1-C6 used an external compatibility runner. | Fold 40-character commit validation and consistent branch/source identity into a future consolidated device-runner overlay; keep old receipts. | OPEN — DEFERRED TO CROSS-SUBSTRATE BATCH |

**Next milestone:** native M1 read-only handshake and read-only observability, then M2 real remote browser, mounts, job states, event cursor, explicit offline/reconnect UX; avoid requalifying passed B1-C6 four-case Android tests just to close unrelated tasks.


### M1-RB — Native app RootService transport and source-device boundary (2026-10-18)

- **Finding:** the old native UI foundation was a permanently unpaired `UnpairedGateway`, so green UI/source checks did not establish daemon connectivity. Root manager behavior and Binder peer identity needed a source-owned implementation and separate device acceptance.
- **Affected:** `Mikeyphw/skybind` Android app, RootService provider, signed build workflow, Devtool `skybind_android_device` qualification and API A4/D1–D3 planning.
- **Remediation:** implemented explicit Connect opt-in and app-owned libsu RootService, per-transaction `Binder.getCallingUid()` and installed package/signing check, root-verified canonical socket path, root peer check, query-only allowlist, fixed JSON envelopes and size bounds, actual state mappers, replay cursor/gap protections, and negative source regression checks. Preserved Jobs versus Activity distinction. No server-side broker listener or mutation enablement.
- **Status:** SOURCE IMPLEMENTED, Android compile/installation/root approval/physical connection NOT_RUN. Existing B1-C6 device PASS remains bound to the previous debug pair. RootService is not cross-app client attestation. Android signing remains ephemeral and requires a persistent secret-backed policy (no key checked in). **Devtool enhancement:** fold native UI, RootService, AIDL, Kotlin contract, real Android negatives and EXO provenance into one product-owned native-app acceptance workflow, instead of emitting an unpaired source-only PASS as device completion.


## M2-N1 — Native remote folder browsing, source 2026-10-18

- **Finding / evidence:** M1 app could enumerate remote names but could not browse any contents. `provider.Browse` in Go already supports read-only bounded `lsjson --max-depth 1`, but RootService did not allow the typed `provider.browse` request. See `internal/provider/provider.go`, `RootReadBridgeService.kt`, and `RemoteBrowserReader.kt`.
- **Projects affected:** Skybind Android app, Skybind daemon/provider, Devtool source/device workflows.
- **Implementation:** Scoped `provider.browse` with validated remote/relative path and read-only query class; typed entry mapping rejects unsafe names/out-of-folder responses; asynchronous ViewModel folder navigator rejects stale completions/disconnected sessions and refuses file-as-folder actions. No write RPCs, credential access, exported service or arbitrary shell.
- **Status:** IMPLEMENTED_SOURCE_ONLY, GitHub compile/device acceptance NOT_RUN.
- **Recommendation:** add real-device navigation/provenance and disconnected stale-cursor acceptance using a test-owned configured remote; after that, implement M2 file metadata, scoped SAF and M3 preview/proof as separate capability gates. Keep cumulative issue open until physical qualification.


## SKYBIND-M2-CI-001 — Hosted instrumentation Kotlin assertion-import regression

- **Status:** Source fix prepared, GitHub build rerun pending.
- **Affected:** `Mikeyphw/skybind` native Android instrumentation sources (`NativeLifecycleTest.kt`, `NativeUiTest.kt`, `RemoteBrowserTest.kt`); Devtool M2 source gate.
- **Evidence:** GitHub Actions run [39196292135](https://github.com/Mikeyphw/skybind/actions/runs/39196292135), exact source `e97e9d4b88f0a8e6ef9a7083facd910691db0cc1`; `:app:compileDebugAndroidTestKotlin` failed with five `Unresolved reference` errors for imported `androidx.compose.ui.test.assertExists` / `assertDoesNotExist`. The production application compiled; no APK pair was uploaded. Source-only tests had not detected invalid package-level imports.
- **Remediation:** Remove only the invalid imports; `SemanticsNodeInteraction.assertExists()` and `.assertDoesNotExist()` are member methods. Add fail-closed checks over the three instrumented Kotlin files to the existing M2 source gate and three negative mutation tests. Keep APK compilation GitHub Actions-only and do not claim a successful APK or device run until verified.
- **Status to close:** New exact-source GitHub Android build must compile both APKs, upload a byte-identified artifact pair, and pass independent source/attestation checks.


## SKYBIND-M1M2-SIGN-001 — Persistent hosted debug signing and guarded transition (2026-10-19)

- **Status:** SOURCE IMPLEMENTED; provision GitHub Actions secrets, rebuild, installed-package replacement and physical Android acceptance PENDING.
- **Evidence:** Hosted source `250f44201014d005f522f96001190945fdeb63b2`, successful APK run `39198019698`, hosted artifact `12162423668`. New certificate `91b8735c3f3637d611e715dff61f49bd4fba4afff6cb7f3a9145453c8354471e`; currently installed app and test certificates both `9b3e1758bf2e623b0905419a568e3d4f0c4c66ba007110554c613ff439511e49`. Android cannot update across unrelated signers. Both app and test bytes differ; these checks are not physical M1/M2 acceptance.
- **Affected:** Skybind Android application, Android instrumentation APK, GitHub-hosted `skybind-android-apks.yml`, Devtool Actions artifact/device gates.
- **Decision:** User explicitly authorizes replacement of the two Skybind packages WITHOUT backing up their existing private app data. Uninstallation deletes that data. No other package, module, root grants or user files are authorized for deletion. Never trigger uninstall automatically in a source/CI overlay.
- **Implementation:** Local owner-provisioned PKCS12 keystore stored outside Git with private permissions; GitHub Actions encrypted keystore/password/certificate-pin secrets; fail-closed build preparation; explicit AGP signingConfig for app+test; certificate equality attestation in hosted manifest; source negative tests; no fallback to ephemeral `debug.keystore`. GitHub remains the sole Android APK builder. GitHub private secret contents are never archived.
- **Next qualification:** Run provisioning on a user-controlled host, push source, run hosted build; verify identical pinned cert on both APKs and GitHub artifact/source identity; compare installed packages; only after successful verification perform the authorized two-package replacement. Run actual native UI read-only RootService / M2 browsing instrumentation, reconcile evidence, keep all former B1-C receipts historical. Preserve the long-lived signing key securely; losing it forces another explicit signing transition.
- **Devtool enhancement:** Add signing-certificate identity pin as a first-class source-bound artifact/EXO constraint and avoid expensive requalification after every artifact when the identity remains stable. Preserve negative evidence, source-gate outputs and explicit user authorizations.

## SKYBIND-SIGN-ARTIFACT-001 — Persistent signer overlay inventory action mismatch (2026-10-19)

- **Status:** Fixed in replacement source-bound Devtool ZIP; application and repository CI pending. No target source changes occurred in the failed attempt.
- **Evidence:** `devtool apply-overlay` run `b6f9ddcd00714bfba0f18969fbd80fd6` stopped at `artifact-check` with `artifact_failure`: inventory actions `create` were unsupported for three new files (`docs/devtool/SKYBIND_PERSISTENT_DEBUG_SIGNING_20261019.md`, `scripts/dev/android/stable_signing.py`, `tests/test_stable_signing.py`); canonical inventory also flagged these payload members as missing. Failure occurred before source application.
- **Affected:** Skybind M1/M2 persistent debug signing artifact assembly; Devtool overlay packaging and validation UX.
- **Resolution:** Replacement bundle declares each new file as `add` and each existing source-bound file as `modify`, with unchanged source preimages, recomputed ZIP/content digests, expected inventory cardinality (5 modify, 3 add), and a packaging-time supported-action check. The real Devtool apply still needs to confirm the corrected bundle.
- **Recommendation:** Devtool/overlay producers should validate inventory action vocabulary and inventory-vs-payload membership before distribution. Provide a fast source-free canonical `artifact-check` command for authors, and report accepted action names directly in failures. Do not weaken the artifact gate to accept ambiguous `create` aliases silently.


## SKYBIND-M2-ESPRESSO-API36-001 — UI instrumentation InputManager.getInstance incompatibility (2026-10-19)

- **Status:** HOSTED DEPENDENCY REPAIR PREPARED, physical rerun NOT_RUN. Earlier device report must remain 19 executed, 10 PASS, 9 FAIL_INFRA; do not relabel failed Compose tests PASS without executing the repaired APK.
- **Affected:** `Mikeyphw/skybind` Android UI instrumented suites (`NativeLifecycleTest`, `NativeUiTest`, `RemoteBrowserTest`), AndroidX Compose test runtime, Espresso, Devtool Android source contract and device qualification.
- **Evidence:** User's installed stable-signed source `a0ea31826173794de7a3f619132eca5fd37ec3c8` instrumentation runner reported `Tests run: 19, Failures: 9`. All nine failures share `androidx.test.espresso.base.InputManagerEventInjectionStrategy.initialize` reflection failure `java.lang.NoSuchMethodException: android.hardware.input.InputManager.getInstance []`; the other 10 security/protocol/model tests passed. This was a framework failure before UI assertions, not a proven native browser logic failure. Historical B1-C evidence must remain unchanged.
- **Cause:** Compose's `ui-test-junit4` transitively pulls an old Espresso Core implementation on this dependency graph. AndroidX Espresso 3.7.0 release notes explicitly fix reflective `InputManager.getInstance()` usage using `getSystemService` instead (https://developer.android.com/jetpack/androidx/releases/test).
- **Repair:** Explicit `androidTestImplementation("androidx.test.espresso:espresso-core:3.7.0")` in `android-app/app/build.gradle.kts` to upgrade the test APK's resolved Espresso runtime; retain existing Compose BOM and production app dependencies. New `scripts/dev/android/m2_espresso_source_gate.py` and negative `tests/test_m2_espresso_compat_source.py` reject missing/legacy/duplicate/commented dependency. No local Android APK compilation, app uninstall, root enablement, or changes to broker or application behavior.
- **Acceptance:** New GitHub-hosted app + instrumentation APK pair with exact commit, persistent-signing pin, source/archive attestation, signed update install (do not uninstall), and reexecution of all 19 tests. Observe all nine formerly blocked tests PASS before marking UI suite green. Separate root approval/live daemon/browser tests still require real device evidence. If failures persist despite 3.7.0 resolution, capture `dependencyInsight` for `debugAndroidTestRuntimeClasspath` and investigate test-runtime injection rather than rewriting production behavior.
- **Devtool improvement:** Include an Android-test-runtime dependency compatibility check and source-bound instrumentation failure classification in the grouped qualification lane. Do not conflate `FAIL_INFRA`, test assertion failures, and `NOT_RUN`, and do not suppress real failures to satisfy a release gate.


## SKYBIND-M2-OFFLINE-SEARCH-ASSERT-001 — disconnected Browser assertion (2026-10-19)

- **Status:** DEVICE REPRODUCED; test-only source repair prepared; new GitHub/device re-run NOT_RUN. The prior 19-case suite is **18 PASS, 1 FAILED_ASSERTION**, not 19 PASS. The previously blocked nine Compose tests are now executing with Espresso 3.7.0; do not relabel the remaining assertion failure or infer live daemon availability.
- **Affected projects:** `Mikeyphw/skybind` native Android M1/M2 Compose fixtures (`NativeUiTest#unpairedStateHidesStaleServerData`) and M2 browser source gate; Devtool test/evidence classification.
- **Evidence:** User's 19-case instrumentation output on persistent-signed commit `5ab7aad6d45f95885bb3965b9ac47beec298e70e`: eighteen individual `INSTRUMENTATION_STATUS_CODE: 0`; one `INSTRUMENTATION_STATUS_CODE: -2`, in `NativeUiTest.kt:81`: `Expected exactly '1' node but could not find any node that satisfies (TestTag = 'browser-search')`; `INSTRUMENTATION_CODE: -1`. No earlier `InputManager.getInstance()` failures were reported. The Browser UI hides both remote items and the search field when disconnected by design; the stale-state test expected a disabled search element that is not rendered.
- **Repair:** Keep the fail-closed production Browser UI unchanged; replace only `browser-search.assertIsNotEnabled()` in the offline-state test with `browser-search.assertDoesNotExist()`. Extend `m2_browser_source_gate.py` to require offline-first Browser branching and the correct assertion, and add negative mutation tests for either mismatch. The online search interaction test remains unchanged.
- **Acceptance:** Github-hosted APK and instrumentation pair built from the exact new commit, verified against pinned persistent signing, installed with `adb install -r` (no uninstall/data wipe), run the single corrected test plus all 19 instrumentation tests. Mark 19/19 only upon actual device PASS. Follow separately with real root permission/connection, daemon RPC and read-only remote navigation acceptance; fixtures do not qualify those.
- **Devtool improvement:** Source-bound CI contract should couple UI visibility conditions and offline/unauthorized assertions rather than relying on isolated syntactic tokens. Distinguish framework bootstrap (the prior 9 blocked cases), assertion regression (this 1 case), live integration NOT_RUN, and release qualification.


## SKYBIND-M2-L1 — Android real RootService/browser automated acceptance (2026-10-19)

- **Evidence:** User-provided physical Android device instrumentation (source after offline-browser test correction) reports **19 executed, 19 PASS, 0 FAIL**, terminal `INSTRUMENTATION_CODE: -1`; the earlier Espresso 3.7.0 startup incompatibility and disconnected-search false assertion no longer appear. This evidence validates included fixtures/navigation/contract cases, but **does not** establish a running app-owned privileged RootService or real daemon browse.
- **Affected:** Skybind native app, RootReadSession, read-only daemon API and Devtool Android product/device qualification. Go provider `Browse` returns bounded `lsjson --max-depth 1` listing; privileged app-owned RootService is the only Android RPC bridge.
- **Implementation:** Added opt-in `LiveRootBrowserAcceptanceTest`, which binds a real RootReadSession, consumes server-authoritative capabilities/status/remotes/jobs/events, browses the selected configured remote root, closes and proves stale state cleared, then rebinds and verifies a fresh snapshot. No fake RPC, local root shell, credential read, mutation, daemon stop, automatic permission grant, hidden remote name logging, uninstall or data clear.
- **Provenance/evidence:** Added `m2_live_device.py` with exact-main GitHub API workflow/artifact inspection, stable APK hash/signature verification, read-only installed APK pulling, ADB identity/SELinux preflight, explicit `--mode live` single-case runner, bounded parser and private write-once sanitized JSON receipts. No unattended install or root grant. Existing 19-test receipt remains historical. `github_run_authenticated` and whole-product `device_qualified` remain false; a real live pass is qualified only under `m2_l1_device_qualified`.
- **Devtool improvement:** This bridges the gap between fixture-only source/device PASS and actual RootService-provider integration. Retain a separate native Actions-06 attestation and full interactive UI/root refusal/death/reconnection gates; source and hosted compile are necessary but insufficient.
- **Status:** IMPLEMENTED_SOURCE_ONLY — Hosted build and real-device live case **NOT_RUN** on this new source. Missing daemon/root grant/remote must report BLOCKED, never a passing acceptance result.


## SKYBIND-M2-L1-CI-002 — Consolidate CI artifact/device entry point (2026-10-19)

- **Evidence:** User supplied `Cinderbox-Companion-20261019-085114-531377.tar.gz`,
  `scripts/devtool/ci_artifacts_device.py` with exact-run `gh` downloads,
  dynamic test lanes and installed APK checks. Skybind had separate manual
  `gh run download` / `adb install` instructions and a read-only standalone
  `scripts/dev/android/m2_live_device.py`; the initial M2-L1 overlay also
  accidentally carried `__pycache__/m2_live_device.cpython-313.pyc`.
- **Affected:** Skybind hosted Android artifact provenance, Termux/ADB device
  workflows, Devtool artifact packaging, M2-L1 RootService qualification.
- **Implemented:** Adapted `scripts/devtool/ci_artifacts_device.py` with explicit
  `--test m2-preflight`/`--test m2-live` lane selection, automatic retrieval of
  a **single combined** GitHub-hosted APK pair and manifest, exact clean HEAD
  vs successful GitHub run source check, signer-pin and APK byte verification,
  safe package introspection, strict opt-in `--install` (same-signer only; never
  uninstall/clear), separate signed JSON summary, no release-overclaim and
  fail-closed mismatches. Delegates M2-L1 execution to the already-reviewed
  `m2_live_device.py` runner. New negative/offline source tests are in the
  grouped Devtool workflow; remove the stray pyc from the revised overlay.
- **Design tradeoff:** Github `gh run download` exposes extracted files, not
  original ZIP bytes, so do not claim an independent artifact ZIP digest check.
  The signed pair is verified against per-APK hashes and certificates in the
  source-bound manifest; the GitHub run/artifact identities are checked online.
- **Status:** IMPLEMENTED_SOURCE_ONLY and validated offline; physical live
  RootService qualification still NOT_RUN. Future milestones should register
  new reviewed lanes in this launcher rather than fork another APK installer.


## SKYBIND-M2-L1-RECEIPT-001 — Nested acceptance receipt self-reference mismatch (2026-10-19)

- **Evidence:** Installed hosted pair from run `39250115149` and artifact `12185650761`, source `ebf261a835f9f4425e98d913d69ea38abb816a42`, passed exact APK verification: `PASS_CI_PAIR_VERIFIED_NO_TESTS_SELECTED`, `installed_pair_verified=true`. The subsequent `--test m2-live` produced `LANE_RECEIPT_SUMMARY_MISMATCH`, `m2_l1_device_qualified=null`, despite matching installed pair. Review of `scripts/dev/android/m2_live_device.py` showed `store(doc)` serialized the JSON before `doc['receipt']` was set; `scripts/devtool/ci_artifacts_device.py` demanded the missing self-reference during acceptance. **The underlying RootService test result was not included in the supplied summaries and must not be inferred.**
- **Affected:** Skybind native M2-L1 real-device runner, canonical `scripts/devtool/ci_artifacts_device.py`, Devtool producer/consumer evidence contract and operator experience.
- **Fix:** Serialize an immutable single-owner per-lane JSON receipt with its own receipt path pre-populated; compare the launcher summary against on-disk receipt (path, state, reason, source, run, artifact, installed-pair and narrow qualification), with fail-closed mismatch. Initialize `m2_l1_device_qualified=false` on all failure paths. Add positive preflight roundtrip and negative absent-path/product-failure regression tests. No APK or daemon changes, no grant requests, no installs or data clearing.
- **Status:** SOURCE FIX PREPARED; host Termux Devtool acceptance and physical `m2-live` still require rerun. Do not reclassify 19/19 fixture tests or installed-pair verification as live-daemon qualification.
- **Devtool cross-project improvement:** receipt writers should add self-referential identity before writing, and parent orchestrators should test nested producer→consumer serialization with real temporary files, not only mocks whose manually constructed receipts accidentally conceal the bug.


## M2-L1 directory `Size:-1` interoperability and redacted diagnostics — 2026-10-19

- **Status:** FIXED_IN_SOURCE; DEVICE_REQUALIFICATION_PENDING (old receipt stays FAILED).
- **Affected:** `internal/provider/provider.go`, Android `RemoteBrowseReader`,
  M2-L1 instrumentation, CI-artifact device runner and grouped Devtool source checks.
- **Evidence:** Hosted run 39264383682, artifact 12193065145 at source b763a59;
  installed pair MATCHED, m2-preflight PASS, m2-live FAILED `SKYBIND_LIVE_FAILED_BROWSE`.
  Real root-only direct bundled rclone `lsjson --max-depth 1` succeeded (~3 sec),
  yielding 23 entries, seven directories with `Size:-1`, zero negative-size files.
  Both original Go and Android parser rejected all negatives.
- **Repair:** allow `Size=-1` *only* on directories at both boundaries, add Go/Android
  regressions for 7 dirs/16 files and negative unsafe variants, categorize browse
  failures without leaking exception text or credentials.
- **Recommendation:** Keep real-provider interoperability fixtures coupled to source
  gates; preserve negative receipts and require exact-source GitHub build/device
  evidence before acceptance closure.


## SKYBIND-Q05-WEBUI-INVENTORY-20261019 — stale fixed-count test blocked hosted native candidates

- **Evidence:** GitHub Actions run `39271557243`, source `3f5140dcea16e74f66b90f1df952855239a2757c`, failed at `Validate packaged WebUI ES module syntax (fail CLOSED)`, while all checked module syntax subprocess invocations preceding the Python test had succeeded. Historical `test_q05p4_webui_esm.py` required exactly `app.js`, `bridge.js`, `flow.js`, `model.js`, and `parity.js`. Skybind now packages five additional JavaScript files: `api_qa_probe.js`, `interactive_qa.js`, `live_progress.js`, `remote_b3_ui.js`, and `remote_transfer_ui.js`. Consequently native Go tests, Android/arm64 daemon compilation and module candidate upload were NOT_RUN; no module artifact was created.
- **Root cause:** An early five-file WebUI inventory assertion was incorrectly treated as a complete, frozen manifest and conflicted with subsequently added legitimate source modules. The syntax validator itself was not the failing component.
- **Fix:** Require the original five core modules to exist but dynamically syntax-check every packaged `.js` ES module, reject symlinks and syntax errors, and add positive/negative tests for added modules, removed core files and unsafe symlinks. Preserve the explicit CI Node ES-module syntax check and historical bad-closure regression. Do not remove or silently skip checks when source expands.
- **Scope:** Q05 candidate build qualification only. This source test repair does not rebuild or authorize Android APKs, root approval, module installation, release sealing or M2-L1 device qualification. The directory-unknown-size fix remains source-implemented pending an updated native daemon and Android reader deployed from matching evidence.
- **Status:** SOURCE-BOUND HOTFIX PREPARED; rerun the hosted native candidate workflow at the new commit, inspect downstream Q04 dependency/pins independently, verify produced native artifacts, and leave release/device qualification false until actual testing.


## SKYBIND-M2-L2 — Read-only real Compose UI and session lifecycle (2026-10-20)

- **Evidence:** M2-L1 real RootService/provider browsing acceptance passed on Android API 36; user-reported receipts show `PASS_M2_L1_PAIR_PREFLIGHT_ONLY` and `PASS_M2_L1_LIVE_READ_BROWSE_REBIND` from GitHub run `39352843961`, artifact `12234555440`, source `c2cb64cdc3528c1de9814eb8ca4880b5aa778b8f`. Existing fixture-only 19/19 also preserved. These prove backend navigation contract but not Compose live navigation.
- **Affected:** Native Android Compose control center, `SkybindSessionViewModel`, Devtool GitHub APK/device runner, optional KernelSU user authorization, session lifecycle.
- **Implemented:** Real-app, opt-in M2-L2 instrumentation (no fixture backend) for Home → Browser → real remote → directory → Up → Remotes, Jobs/Activity separation, Activity recreation, explicit app-local unbind, stale data hiding and explicit reconnect. Added UI Disconnect (does **not** revoke root grant or stop daemon) and `m2-ui-live` lane; source-bound JS-free Python validation and negative receipts preserve independent M2-L1 results.
- **Coverage limits:** Manual interruption of daemon/root-service process, real permission revocation, unobserved lazy-list items, backend mutations, and full release security require distinct gates; no automatic reboot, uninstall, root calls or data clear. If no selectable remote folder exists, return BLOCKED rather than auto-creating test data.
- **Status:** IMPLEMENTED_SOURCE_ONLY; Android hosted compilation and physical M2-L2 execution not yet performed. Do not relabel M2-L1 as M2-L2.
- **Devtool improvement:** Typed lane registry with independent narrow qualification flags and source/run/artifact/signer/installed-byte proof; tests for sibling lane not overclaiming qualification and for hidden stale UI.


## SKYBIND-M2-L2-ARTIFACT-001 — Unsupported Devtool `create` inventory action (2026-10-20)

- **Evidence:** Devtool apply-overlay run `246257fa140240e392a46d80e309fadb` failed during `artifact-check` before applying any source. Canonical qualification rejected `action: "create"` for `LiveUiAcceptanceTest.kt`, `m2_ui_live_source_gate.py`, and `tests/test_m2_ui_live.py`; it then reported the same three payload paths missing from accepted inventory.
- **Affected:** Skybind M2-L2 overlay packaging, Devtool producer/schema interoperability, downloadable artifact operator workflow. Native Go daemon, root grants and Android application state were not changed by this failure.
- **Cause:** The ZIP generator used `create` instead of Devtool's supported new-file `add` inventory action. Existing-file action `modify` and source preimage pins were already correct.
- **Repair:** Reissue one replacement atomic ZIP with exactly three `add` declarations and eleven `modify` declarations, recomputed inventory SHA-256 for this ledger, stable validation-script digest, updated outer ZIP hash and SHA256SUMS.txt. No app/test logic changes versus the original M2-L2 payload.
- **Prevention:** Add a producer-side pre-shipment manifest action enum check (`add`/`modify`) and require canonical artifact qualification on the generated ZIP before sharing. Never equate source-only test passes with Devtool artifact acceptance.
- **Status:** ZIP INVENTORY CORRECTED; local source/tests and manifest checks PASS; actual Termux Devtool apply/release qualification pending. Preserve the failed run as evidence, do not rewrite it.


## SKY-M2L3-NEG-20261020 — Isolated negative-lane receipts and superseded binder callbacks

- **Status:** Source remedy in proposed M2-L3 overlay; hosted AndroidTest compilation and real device qualification pending.
- **Affected projects:** Skybind Android app, Devtool CI artifact -> installed APK lane registry, real-device instrumentation.
- **Evidence:** M2-L1 run `39352843961` and M2-L2 run `39363846767` passed narrow scopes at separate SHA identities; neither exercised abnormal binder lifecycle or fail-closed negative browse. `RootReadSession.onServiceDisconnected` previously did not check whether the callback belonged to the current binding. A superseded callback could clear a newer session, while `close()` invalidated its connection reference only *after* unbind.
- **Change:** Ignore old binding callbacks by comparing the callback identity to `connection`; retire the reference before unbind. Register `m2-negative-live`, a separate exact-source/signature checked real RootService negative-boundary lane. The parser and host aggregator refuse skip, duplicated results, wrong source, wrong artifact, cross-lane promotions, and incompatible scope flags. Expose source-only regression as a two-node Devtool DAG and wrapper command; no local APK build.
- **Limits:** This lane does not prove denial after real KernelSU revocation, real daemon process death, full app force-stop/relaunch, or cross-UID BKX/chrootctl grants. Those require independent opt-in and signed receipts; do not mark M2-L3 fully qualified from this sublane alone.

## 2026-10-20 — Skybind M2-L3 consolidated lifecycle follow-up (source-only pending hosted/device)

- **Evidence:** M2-L3 read-only negative lane passed on GitHub-hosted run `39427946191`, artifact `12267026065`, exact source `7cb78fde4b07d3b9d34e2e78b5f2839fc4626115`; user-reported device receipt located at `.../ci-20261020T132620319975Z-dcf336cd/summary.json`. Earlier M2-L1 and M2-L2 passes remain separate historical qualification.
- **Issue (observed in source):** `RootReadSession` retained its Binder after RPC exceptions, allowing `connect()` to no-op against an expired session, and lacked a guarded way to exercise app-owned unexpected local transport loss as an independent real-session lane. Actual process stop had no separately opted-in external coordinator.
- **Remediation prepared:** one meaningful grouped overlay adds app-owned transport-loss teardown, callback/concurrency guards, controlled live loss and explicit reconnect, opt-in app-package-only force-stop/cold-launch UI checks, strict narrow receipt validation, and three-node source/fixture/security Devtool DAG.
- **Status:** SOURCE-IMPLEMENTED; 76 M2 Python regressions and 15 CI/device-runner Python tests PASS. Hosted Kotlin APK compilation and new device lanes remain pending. Root-grant revocation and privileged daemon kill intentionally NOT_TESTED. Do not advance A1–E/R0–R6 or formal release based on this scope.
- **Affected paths:** `android-app/app/src/main/**/RootReadSession.kt`, AndroidTest `LiveTransportAcceptanceTest.kt`, `scripts/dev/android/m2_live_device.py`, `scripts/dev/android/m2_process_live.py`, `scripts/devtool/ci_artifacts_device.py`, `.devtool.toml`, source gates and regression tests. Recommended future Devtool integration: contract-driven native instrumentation/pair receipt schema and operator opt-in policy, rather than proliferating unrelated device scripts.

## SKYBIND-M3-OPS-20261020 — consolidated operation UI and qualification lanes

- **Status:** Source changes bundled, Python checks pass locally; hosted Kotlin
  compilation and exact-source real-device preview are NOT YET qualified.
- **Evidence:** M2-L3 negative run `39427946191`, source `7cb78fde...`; M2-L3
  transport/process run `39442535828`, source `def2d872...`, both selected lanes
  passed on user-provided original device summary, historical receipts preserved.
- **Affected:** `RootReadBridgeService.kt`, `IRootReadBridge.aidl`, `RootReadSession.kt`,
  `SkybindSessionViewModel.kt`, `LiveReadSnapshotReader.kt`, `SkybindApp.kt`,
  `ci_artifacts_device.py`, `m2_live_device.py`, new M3 source/device gates.
- **Finding:** The old M2 app intentionally disabled all job commands although
  existing daemon already supports durable, typed `job.run.preview`/`job.run`
  plus `operation.cancel`. Giving the app a generic root RPC or unscoped
  cancellation would violate owner separation and proof policy. Separate
  explicit session-scoped Binder methods retain a one-use daemon proof in the
  privileged process and restrict cancellation to IDs launched in that session.
- **Fix:** One consolidated source-bound M3 overlay with proof-expiry, explicit
  confirmation and copy consent, no automatic retry, progress/event refresh,
  read-only live preview gate, strict receipt scopes, M1/M2 guard updates,
  and grouped Devtool DAG.
- **Remaining obligations:** hosted AndroidTest Kotlin compile; real configured
  check/copy preview PASS (missing job = BLOCKED); dedicated disposable owned-job
  execution and cancellation acceptance before promoting write-capable scope;
  sync destructive preview/consent gate; owner persistence/recovery policy;
  BKX/chrootctl provider compatibility; full release and independent attestation.
- **Tooling improvement:** source gates must guard the *method-specific* read-only
  class, rather than prohibiting every `"job.run"` token in the privileged
  service; otherwise a properly authorized future capability is incorrectly
  treated as a regression. M1/M2 gates now assert separation and exact checks.


### M3 registry nil-slice contract and masked Android snapshot failure — 2026-10-20

- **Evidence:** `Mikeyphw/skybind` commit `296141ac01f2b0716b52d16169bae0f0de2b3e27`, GitHub run `39465999694`, authenticated artifact `12284827401`; same-device `m3-preview-live` produced `BLOCKED / SKYBIND_M3_BLOCKED_DAEMON`. Direct Termux-root daemon RPCs passed for capabilities/runtime/remotes/mount/events, but `jobs.status` had `runs` as an array while `registry.jobs` was not an array. ADB shell root `su` unavailable on `emulator-5554` does not negate Termux-root daemon health.
- **Root cause (source confirmed):** `internal/jobs/jobs.go` `clone()` used `append([]Job(nil), r.Jobs...)`, yielding nil for an empty registry; JSON returned `null` rather than mandatory `[]`. Android `LiveReadSnapshotReader.kt` used `getJSONArray("jobs")` and disconnected; M3 instrumentation collapsed all non-ONLINE snapshots under `SKYBIND_M3_BLOCKED_DAEMON`. Go tests previously covered `runs:[]` only, missing `registry.jobs`.
- **Correction:** fix producer nil-slice conversion in both `jobs.status` and `jobs.snapshot`; constrain consumer legacy-null compatibility to explicitly present field plus schema/revision validation; retain malformed/missing fail-closed behavior; expose only sanitized stage indicators; add Go, Kotlin, Python negative regressions and grouped M3 registry Devtool source node. No daemon state mutation or root reset.
- **Status:** SOURCE_IMPLEMENTED; local regression PASS pending final overlay validation; hosted Kotlin compile, exact signed APK installation/device preview and any Go daemon module replacement **NOT QUALIFIED**. Empty registry must still produce `SKYBIND_M3_BLOCKED_NO_ELIGIBLE_JOB` instead of fake success.
- **Next Devtool improvement:** keep producer→consumer wire-shape test fixtures (including empty/nonempty/null/missing), independently scoped evidence, `RUN_ID` environment variable in commands and `--serial emulator-5554`; do not infer root privileges from ADB shell on Termux-backed target.

### M3 consolidated disposable exact-job qualification — 2026-10-20

- **Evidence:** M3 real preview PASS on user-provided run `39472233849`, SHA `af35406346680e2a813811127a88f07cee381053`, artifact `12287538216`. Previous snapshot blocker repaired and manual-only preview fixture proven. Historical M2 evidence retained, no rerun.
- **Finding:** Proof-bound preview alone does not establish real execution or exact owner cancellation. A naive device run could launch arbitrary configured jobs, race a short job and falsely qualify cancellation, or leave unowned temporary files.
- **Remediation:** single source-locked M3 Devtool overlay with one deterministic media-only/manual-only `check` fixture, explicit prepare/remove authorization and strict path/ownership validation, two opt-in Android instrumentation lanes for start→terminal event and exact app-owned cancel, fail-closed cancellation-race classification, and independent source-only CI/Devtool DAG + cumulative tests. User's `$RUN_ID` and `--serial emulator-5554` retained.
- **Affected:** `scripts/dev/android/m3_disposable_fixture.py`, Android `LiveM3DisposableAcceptanceTest.kt`, `scripts/dev/android/m2_live_device.py`, `scripts/devtool/ci_artifacts_device.py`, new source gates/unit tests, `.devtool.toml`, `.github/workflows/skybind-source.yml`, docs.
- **State:** source validation only; hosted Kotlin compilation and both new device lanes pending. No automatic execution, root grant changes, daemon restart, app force-stop, arbitrary job, copy/sync, or release qualification. Cancellation may truthfully BLOCK if the job finishes before the request.
- **Next:** after real device receipts, reconcile progress/event semantics and configurable copy write consent separately; preserve BKX/chrootctl compatibility in unified API roadmap.

## M3 consolidated COPY/replay and consumer source-conformance expansion — 2026-10-20

- **Evidence:** M3 disposable CHECK terminal run and session-owned cancel independently PASS on GitHub run 39491360742, source `d00f222a79c117fb57909df6dc1d02fa60e574bc`, artifact 12296760416. Prior M3 preview/M2 device receipts remain accepted; no rerun or inference of release qualification.
- **Affected Skybind:** `android-app/.../LiveM3CopyAcceptanceTest.kt`, `scripts/dev/android/m3_copy_fixture.py`, `scripts/dev/android/m2_live_device.py`, `scripts/devtool/ci_artifacts_device.py`, `.devtool.toml`, `skybind-source.yml`, new negative/source tests. **Improvement:** opt-in local copy with independent pre/post exact path, sentinel, membership and SHA-256 validation, reconnect-safe status/event replay and cross-session proof/cancel denial. SOURCE_TESTED; GitHub Kotlin compilation and new real-device copy receipt NOT_YET_RUN.
- **Negative risks:** duplicate claim, stale proof, foreign cancel, already-complete cancellation race, lost event cursor, partial writes, foreign file intrusion, modified sentinel, symlink escape. Copy and evidence gates fail closed; check/cancel historical PASS does not close remote copy or destructive sync. Device status PENDING.
- **BKX/chrootctl consumer contract:** October 20 chrootctl Go native-rclone source snapshot SHA-pinned in `docs/contracts/rclone-compat/M3_CONSUMER_CONFORMANCE.json`; BKX is historical offline inventory only. R1 real caller identity/broker, R2 metadata, R3 duplex streaming, R4 immutable publication, R5 Restic repository transport and R6 migration remain UNQUALIFIED. **Improvement:** source-audited compatibility matrix, no credentials or root tunnel, exact source drift detection; consumer-facing runtime still NOT_IMPLEMENTED. Next: independently validate actual BKX app process UID/SELinux and chrootctl root-module client provenance before transport access.
- **Devtool DAG:** `m3-consolidated-source` five-node dependency graph separates source contract, R0 audited consumer source, negative tests, regression and hosted-only policy. No on-device mutation in workflow. Qualification requires an externally authenticated GitHub Android build and explicit fixture/live commands. Retain durable source/receipt mapping and prohibit false cumulative qualification flags.

## M3-R0-COMPAT — Consumer source pins incorrectly constrain independent BKX/chrootctl development

- **Status:** Consolidated M3 source remediation implemented; live R1–R6 cross-app access remains NOT_QUALIFIED.
- **Evidence:** Supplied chrootctl October 20 snapshot had a source-hash-gated R0 checker. User confirmed BKX and chrootctl continue independent development, and an exact consumer file hash must not compel repeated Skybind APK/module rebuilds. BKX historical 9-case offline contract is not live acceptance.
- **Affected:** `scripts/dev/android/m3_consumer_contract_gate.py`, `docs/contracts/rclone-compat/`, M3 Devtool copy/reconciliation DAG, external app/provider SDK roadmap.
- **Change:** Separate provenance SHA-256 from runtime compatibility, establish `skybind-rclone-consumer-abi-v1` (capability/major-version based), independently submitted consumer requests, optional strict historical audit, negative tests for unknown ABI/command/credentials/unsupported feature, and a no-automatic-fallback policy. Preserve the frozen 57-operation CFS1 catalog.
- **Acceptance:** R0 source/declaration tests can PASS independently of consumer commit identity; unsupported external capabilities report BLOCKED and `runtime_qualified=false`. Actual BKX app UID and chrootctl root-module identity/grants, stream/Restic parity, revocation, and live process tests remain pending.
- **Next:** Build R1 authenticated, revocable gateway and independent updateable adapter **once**, then advance R2–R5 capability tiers using separate consumer-side conformance artifacts. Only a new ABI/unsupported feature/security change should require a new Skybind core build.


### 2026-10-20 — M3 COPY registry compatibility / wrong-source hosted build (COPY-R1)
- **Evidence:** `m3_copy_fixture.py prepare --apply --files 128` → `BLOCKED: COPY_REGISTRY_INVALID`; installed daemon's `jobs.status.registry.jobs` legacy explicit-null empty slice. Previous `m3_disposable_fixture.registry()` handles that representation. Device runner `m3-copy-live` → `REMOTE_BUILD_IDENTITY_OR_STATUS_INVALID` for GitHub Actions run `39503382285`: hosted HEAD `d00f222a79c117fb57909df6dc1d02fa60e574bc`, Termux HEAD `74c50ff50a2ea04badf3f41f78801066cb82f69a`; GitHub build itself successful but wrong source.
- **Root causes:** inconsistent JSON-empty-list compatibility at a consumer fixture boundary; hosted workflow was dispatched before matching source reached GitHub `main`, while source-matching qualification gate correctly refused old APKs.
- **Affected:** `scripts/dev/android/m3_copy_fixture.py`, `tests/test_m3_copy_consolidated.py`, `scripts/dev/android/m3_copy_source_gate.py`, COPY acceptance instructions and evidence.
- **Change:** accept explicit `jobs: null` as empty only when key exists; retain fail-closed missing/malformed registry and no unverified mutation; add exact negative unit/source gates; document immutable commit/run identity checks.
- **Status:** SOURCE FIX IMPLEMENTED / TARGETED REGRESSION REQUIRED / NEW MATCHING GITHUB BUILD AND DEVICE COPY QUALIFICATION PENDING. M2/M3 historical PASS unchanged. Do not bypass GitHub SHA requirements.

## R1-GRANT-FOUNDATION — Dynamic independently upgradeable consumer authorization (2026-10-20)

- **Evidence:** Historical M3 preview PASS GitHub `39472233849` (SHA `af35406346680e2a813811127a88f07cee381053`, artifact `12287538216`); disposable check and session-owned cancel separately PASS GitHub `39491360742` (SHA `d00f222a79c117fb57909df6dc1d02fa60e574bc`, artifact `12296760416`); newly received COPY terminal/reconnect/SHA256/sentinel PASS GitHub `39506914420` (SHA `bb51363442ca5db139b37970dd67318df2914971`, artifact `12303382572`). These are user-supplied authenticated scopes, not one blanket device/release PASS. GitHub `main` verified at `bb51363442ca5db139b37970dd67318df2914971` before the overlay.
- **Finding:** Source hashes for BKX/chrootctl are audit provenance only. The external R1 transport is currently absent, so exposing unscoped CLI/root calls or pretending the October 20 chrootctl binary is an eternal pin would be unsafe and hinder independent consumer updates. Historical receipts across different commits require a trusted cross-scope aggregation that does not erase negative/blocked cases or conflate source commits.
- **Affected:** existing `internal/brokergrant`, `internal/brokeripc`, `internal/brokerissue`, extended `internal/brokeridentity/android.go` + new `root.go/root_test.go`; `scripts/dev/android/r1_consumer_source_gate.py`, `scripts/dev/android/m3_evidence_reconcile.py`, `tests/test_r1_consumer_access_contract.py`, `.devtool.toml`, `.github/workflows/skybind-source.yml`, and the R1 contract documentation.
- **Change:** **Reuse the existing brokergrant/brokeripc/brokerissue authority**, rather than adding a second engine. Extend brokeridentity with a sealed chrootctl root-module identity verifier and require exact measured SELinux labels on both the BKX app-UID and chrootctl root-workload paths, preserving process-start-time double-snapshots; never rely on root UID or historical consumer source SHA alone. A read-only M3 evidence aggregator checks native receipts/signer/run IDs per scope and keeps release qualification false. Six-node Devtool source DAG and hosted source-only tests added.
- **Status:** R1_POLICY_SOURCE_IMPLEMENTED; targeted Go/Python source negatives passing locally. External IPC, real identity attestation, grants backed by OS evidence, read metadata, consumer adapter, R2–R5, APK/module integration and release all **NOT_IMPLEMENTED / NOT_QUALIFIED**. No consumer source version or SHA restriction is created.
- **Next Devtool improvement:** real BKX app-UID + chrootctl root-module SELinux/workload identity measurement, then build an opt-in versioned local broker with explicit user grants and real metadata-only conformance. Preserve GitHub-only Android APK compilation, avoid rerunning already-green M2/M3 device lanes merely due to independent consumer releases, and record new formal evidence separately.


## 2026-10-20 — R1 installed BKX/chrootctl device trust and scoped consumer broker

- **Device observation:** BKX `com.mikeyphw.bkx.android` UID 10327 / version 1.0.0, chrootctl 1.3.7 root-owned sealed runtime/manifest were observed; no running processes or trusted signer/seal attestation in these records. The installed chrootctl manifest digest is `843f470dad66d65d15e7ff0f8178b7d363703f97e46f80966ddad65344c221d4`; binary digest `6280207bb5cc0abd95d9e13204e814b012a25b7ead9003f0ae9e00fed8e490f5`. Do not treat snapshot hashes as permanent Skybind version pins or as grants.
- **Source improvement:** Add `internal/brokeridentity/attested_package.go` typed Android PM signing authority, `module_installed.go` kernel /proc exe + root-owned package manifest operator-pinned verifier, and `multiplex.go` distinct BKX/root verification routes. Extend existing broker stack, do NOT duplicate grant stores.
- **External access safety:** Add explicit-activation root:BKXUID private Unix `ConsumerSocket` with no production auto-start; denial, revocation and bounded connection tests. Android package verifier in `R1PackageManagerAuthority.kt` remains an unconnected platform adapter pending trusted transport; it is not independently attested by a client-provided JSON value.
- **Source and validation:** Go positive/negative tests, Android Kotlin hosted-only compile source, `r1-device-trust-source` DAG and `r1_device_trust_source_gate.py` with fail-closed capability/auto-start negatives; source-only implementation ≠ live R1 qualification.
- **Remaining BLOCKED work:** implement and device-attest authenticated Android-to-Go PM authority, independently approved installed-module seal/SELinux observations for active chrootctl PID, operator-controlled grant delivery, scoped read-only provider backend and actual BKX UID tests; R2–R5 native-rclone semantics, streams and Restic remain unimplemented.
- **Preserved:** four independent M3 device PASS receipts (preview, disposable CHECK, session cancel, local COPY), previous M2 passes, cumulative negative receipts, whole-M3/product/release flag false.


## 2026-10-20 — R1 hosted Android Kotlin compile-blocker: UserHandle.identifier

- **Observed failure:** GitHub Actions `skybind-android-apks.yml` run `39526292566` on source SHA `47fb70e73ce1792951fd524ff9b4ebe8708dbc98` failed during `:app:compileDebugKotlin` at `R1PackageManagerAuthority.kt:43:65`: `Unresolved reference 'identifier'`. Hosted signing/source gates passed; compilation failed and no APK artifact was produced. This is a source code defect from the R1 trusted consumer broker overlay, not a root, signer, BKX, or chrootctl installation failure.
- **Remediation:** Retain the exact PackageManager-reported UID check and the separately approved Android user ID, comparing the user partition of the UID (`uid / 100_000`) without relying on hidden Android `UserHandle` APIs. Apply identical SDK-safe mapping to the R1 instrumentation test and add a wrong-user negative case. Add source guard preventing hidden `UserHandle.identifier`/`getIdentifier()` calls and a negative regression test for that guard.
- **Safety:** Source-bound only, no grants, external socket activation, app or module mutation, credentials, and no BKX/chrootctl rebuild. The R1 trusted platform bridge and real-process attestation remain unqualified; M2/M3 historical acceptance remains intact.
- **Status:** SOURCE_REPAIR_PREPARED; Android Kotlin compilation still requires a fresh hosted GitHub run from the repaired exact source. Do not mark hosted build or R1 device acceptance PASS based on Python checks alone.

## 2026-10-20 — R1 trusted consumer admission source foundation and live PM qualification split

- **Evidence:** GitHub hosted APK run `39528230023` successfully compiled Kotlin correction at source `82436bd3682ca150b858a12be6e0db806230f2ae`; no R1 external provider device qualification. BKX PM UID 10327 and chrootctl module manifest/binary hashes are read-only installed observations. Earlier M3 four-scope receipt reconciliation `PASS_FOUR_INDEPENDENT_M3_SCOPES` preserved; whole M3, external provider and release not promoted.
- **Gap exposed:** existing `PlatformPackageAttestor` has an abstract `PackageAuthority`; R1 Kotlin `PackageManager` verifier existed but was not linked to Go. `ConsumerSocket` existed without a vetted operator admission policy, and starting a listener before trust linkage would be unsafe. Neither consumer currently issues broker requests through an accepted adapter.
- **Implemented:** one strict root-owned 0600 versioned operator-policy parser with nested JSON duplicate denial, unique scope, bounded grant TTL, signer/module-seal/SELinux identity pins and no source-commit/version locks. `brokerruntime.Gateway` composes existing single-authority R1 broker grant/identity/IPC/issuer; fails closed without trusted PackageManager, module, `/proc` and backend dependencies. Positive and negative Go tests cover missing authority, spoofed BKX/chrootctl principals, scope escape, overbroad mutation, token revocation and changed process/package; full source-only DAG.
- **Android test-only:** BKX package-visibility declaration and opt-in, independently approved signer/UID PackageManager instrumentation test; source-bound hosted pair PM-observation runner, with explicit scope `PM_ONLY_NO_GO_TRUST_LINK` and no provider qualification claim. APK built on GitHub only. This is not evidence that BKX itself can connect to the provider.
- **Still pending / must not claim:** trusted Android-to-Go PM channel, active independently attested chrootctl PID, real BKX executable/UID/SELinux connector, operator token delivery to authenticated client, read-only metadata backend and denial/revocation device matrix. Maintain the installed native rclone of both consumers and avoid forced rebuilding them for unrelated changes. Record this gap until an independently attested R1 external-provider acceptance succeeds.

## 2026-10-21 — R1 authenticated Android-to-Go PM channel and 3-case device gate

- **Evidence:** BKX PlatformManager approved signer observation `PASS_R1_BKX_PLATFORM_PM_OBSERVATION_ONLY`, run 39532482009, artifact 12316097658, SHA 627fce0285deb07e8f2252c65a2f86fec5ccf6f7, while `trusted_android_to_go_bridge_qualified=false`, no grants, no live BKX/chrootctl process observations. This is NOT external provider qualification.
- **Root-cause limitation discovered:** existing filesystem consumer socket's parent `/data/adb/skybind` 0700 blocks Android app UID traversal even if its child socket is 0660. Do not weaken root-owned private state directory. Production consumer connection/routing remains an explicit open security and reachability issue requiring separate listener redesign and device SELinux validation.
- **Implemented:** `PMBridge` challenges a pinned Skybind app process over Android abstract Unix socket, checks kernel SO_PEERCRED UID/PID/GID, `/proc` process UID/SELinux/start ticks before/after, rejects duplicate JSON/replay/oversize, and delegates installed BKX certificate decision to existing `PlatformPackageAttestor`. UI-process `R1PMBridgeAgent` responds using PackageManager DER signing info only while Skybind UI is visible; no automatic root broker startup or grants. Operator-supplied authority UID and SELinux pins are mandatory. Added 3-case source-bound device runner (valid, signer denial, wrong authority UID denial) and hosted Android-arm64 Go diagnostic workflow, Android instrumentation negatives, Go adversarial tests, Python offline runner tests, new five-node Devtool source DAG, hosted source gate.
- **Status:** SOURCE_IMPLEMENTED; Go suite and source tests passed in isolated full-source reconstruction. Android Kotlin hosted compile and real-device abstract-socket/SELinux connection NOT YET QUALIFIED. Production Go must additionally independently verify Skybind authority-app signing lineage prior to granting real read access. Consumer socket redesign, active chrootctl process attestation, BKX/chrootctl separately deployable adapters and operator-controlled token delivery remain TODO. No change to BKX/chrootctl native-rclone fallback, no M2/M3 retest, no credentials or backup mutation.


## 2026-10-21 — R1 Android-to-Go PM channel overlay audit and repaired device test coverage

- **Evidence:** original `SKYBIND_R1_ANDROID_GO_AUTHORITY_MULTI_CASE_DEVTOOL_20261021.zip`, bound to GitHub main `627fce0285deb07e8f2252c65a2f86fec5ccf6f7`; the Go diagnostic contained three intended live cases, and Android's `R1PMBridgeAgentTest.kt` contained four negatives, but `r1_pm_bridge_device.py` did **not** execute those Android negatives. The runner also allowed omission of `--restart-skybind`, so the short-lived app-side bridge might not reconnect between diagnostic cases. Device Go receipts were verified only by their state/reason, not independently by the claimed identity/grant flags.
- **Correction:** one consolidated replacement overlay, same GitHub source-bound preimage. Run all four named Android instrumentation negatives using the installed source-verified APK pair before Go diagnostic; check complete runner receipts even if adb returns shell success. Require `--restart-skybind` for three independent Go authority handshakes; validate positive/wrong-signer/wrong-authority identity flags independently, and prohibit consumer-grant/provider assertions. Add offline synthetic positive and malformed/replay-like acceptance tests, require test coverage in R1 source gate, preserve exact preimage SHA, ZIP SHA256SUMS, and existing cross-campaign regressions.
- **Status:** **REPAIRED_SOURCE_ONLY**. Go and Python source regressions PASS locally; no Android device / SELinux / trusted Go channel result has yet been submitted for this repaired source, and no APK compiler result is claimed. Seven scoped device cases **NOT_RUN**. Consumer broker remains **DISABLED**, and real BKX/chrootctl clients, module process attestation, revocable live access and release qualification remain **NOT_QUALIFIED**. M3 four historical PASS scopes are preserved without retesting.

## 2026-10-21 — R1 PM channel Termux Unix socket fixture EINVAL recovery

- **Evidence:** Devtool `apply-overlay` run `89b6ae563ec341f09e6fc864416abfba` failed the required `go test ./...` after 86 R1, 122 M-series and 15 runner tests passed. `internal/brokeridentity.TestPMBridgeRealUnixRoundtripToPlatformSigner` attempted to bind an on-disk Unix socket under Termux `$TMPDIR` plus `testing.T.TempDir`, exceeding Linux `sockaddr_un.sun_path` (108 bytes) and returning `bind: invalid argument`. Devtool **correctly rolled back** all 15 source paths and preserved the failed validation evidence. This is a **test-fixture bug**, not evidence that the Android-to-Go production abstract socket is broken.
- **Fix:** Keep source-bound preimage `627fce0285deb07e8f2252c65a2f86fec5ccf6f7` and consolidated 15-file overlay. Replace only the filesystem-bound Go fixture address with a per-test unique, short Linux abstract socket using a SHA-256 digest of `t.TempDir()` as the uniqueness seed. Explicitly check the encoded name remains within Linux `sun_path` and prohibit regression to `filepath.Join(t.TempDir(), ...)` through the offline R1 source test. No production listener, trust model, grants, consumer adapter, BKX/chrootctl files, or M3 scope changes.
- **Qualification:** Android Kotlin hosted compilation and seven real-device cases **PENDING**. Running the Go fixture successfully verifies only local protocol round-trip. External provider, installed consumer attestation and release qualification remain **false**.


## 2026-10-21 — R1 PM peer attestation rejected Android /proc NUL terminator

- **Real-device evidence:** R1 bridge receipt `r1-pm-bridge-eee2c5be6bee49fd847955bd5761b884.json`, source `9ae3ba9cb970a96246d0ff948c8138351da4ac1c`. Four Android agent negative instrumentation tests passed. Positive Go channel returned `AUTHORITY_PEER_NOT_ATTESTED` with `pm_channel_authenticated=false`; no grants, consumer access, M2/M3 retests or release qualification. Independent root Termux command emitted `ignored null byte in input` reading `/proc/<PID>/attr/current` for Skybind PID 20746, UID 10335, approved label `u:r:untrusted_app:s0:c79,c257,c512,c768`.
- **Root-cause hypothesis supported by code:** `brokeridentity.PMBridge.verifyPeer` compared `strings.TrimSpace(string(label))` to approved context; TrimSpace does not remove NUL, while Android `/proc/<PID>/attr/current` may have a terminal NUL. The identical comparison in `AndroidVerifier` and `RootVerifier` was a latent shared failure. The receipt does not by itself exclude socket SELinux policy or other peer rejection, so do not claim a device-confirmed root cause until a retest.
- **Repair:** strict `procSELinuxLabel` parser accepts no terminator, one trailing NUL/LF, or one of each, never embedded NUL or a mismatched label. Apply to all three verifiers, with Go positive/negative tests and source regression. Explicit root diagnostic now distinguishes SELinux mismatch vs no connection timeout without weakening any checks; wrong authority UID remains `AUTHORITY_PEER_NOT_ATTESTED`.
- **Qualification:** source validation pending independent Termux apply and GitHub hosted diagnostic refresh; live seven-case `pm_channel_qualified=false`; BKX/chrootctl consumer clients, trust-channel signer anchor, external provider and release remain BLOCKED. Previous four M3 device PASS scopes preserved without rerun.

## 2026-10-21 — R1 PM authority real-device qualified; consumer abstract transport source candidate

- **New independent device evidence:** user supplied `r1-pm-bridge-bf07ded28099404ea3b9183d4345c1c4.json` at source `7ba88071f6e3446316948c4789c80d33be7963ee`. State `PASS_R1_ANDROID_TO_GO_PM_THREE_CASES_PLUS_FOUR_AGENT_NEGATIVES`; positive authenticated PM observation, wrong signer denied, wrong authority UID denied, four Android malformed/foreign-input tests passed. `pm_channel_qualified=true`; `bkx_process_attested=false`, `chrootctl_process_attested=false`, `grants_issued=false`, `external_provider_qualified=false`, `release_qualified=false`. This supersedes earlier PM-only/failed-peer diagnostics for that *one scope*, without rerunning M3.
- **Blocker / architectural finding:** the previous read-only `brokeripc.ConsumerSocket` used `/data/adb/skybind/consumer-gateway/consumer.sock`, where the root-only `0700` parent makes the filesystem endpoint inaccessible to BKX UID 10327. Making private parent world-executable would compromise the directory policy. Tests using root as a client had not qualified real Android app access.
- **Fix staged as source:** `AbstractConsumerSocket` provides a fixed-name Linux abstract endpoint, root-only explicit activation, bounded connections, kernel peer verifier, existing token store, revoke and exact remote/prefix semantics. `RequestOnce` provides Go request framing without arbitrary endpoint selection or native rclone mutation. `Gateway.StartAbstract` refuses missing/disconnected Android PM authority or noncanonical module attestor; ordinary module/app startup never calls it. Add real-root host socket tests and root-only CI source checks, five-node Devtool `r1-consumer-transport-source` DAG, contract document and offline source negative tests.
- **Truthful status:** SOURCE_IMPLEMENTED / HOST_ROOT_POSITIVE_PENDING_GITHUB; **real BKX/chrootctl transport NOT_QUALIFIED**. Android SELinux may still prohibit abstract socket reachability. The Skybind app signer trust anchor outside its own PM authority, live chrootctl `/proc/<pid>/exe` attestation, independently deployed BKX/chrootctl clients, secure operator token handoff, typed remote metadata backend, live grant/revoke and external release gates remain open. No automatic listener/grants, BKX/chrootctl rebuild, rclone credential sharing, remote access, backup mutation or M2/M3 device retest.

## 2026-10-21 — R1 read-only metadata, exact-process grant handoff and cross-repo adapters

- **Evidence:** user device receipt `r1-pm-bridge-bf07ded28099404ea3b9183d4345c1c4.json` gives `PASS_R1_ANDROID_TO_GO_PM_THREE_CASES_PLUS_FOUR_AGENT_NEGATIVES` at source `7ba88071f6e3446316948c4789c80d33be7963ee`, for *only* the authority channel; prior M3 four independent device scopes remain PASS. Existing gateway source has abstract IPC, but no production metadata backend, consumer token handoff or real BKX/chrootctl adapters.
- **Root cause/architecture:** the earlier filesystem socket is behind root-only directory; abstract transport fixes pathname reachability, but tokens must not be passed via Termux shell, app Intent, config files or unverified JSON, and every remote operation must be implemented by a bounded typed executor rather than a generic RC proxy. Installed chrootctl 1.3.7 must not be treated as rebuilt merely because Skybind source changes.
- **Source changes:** provider-backed read-only metadata reader; one-off kernel-exact-PID grant handoff with policy-scope checks, short TTL and revoke; explicit root operator-only diagnostic; independent operator-approved Skybind APK **byte-seal** check; read-only live chrootctl PID verifier and hosted diagnostics; separately source-bound opt-in chrootctl CLI source adapter; BKX Kotlin adapter reference (not installed). Preserve process-incarnation safety, no auto-start, no native fallback mutation, no M3 retests.
- **New qualification barriers:** Trust in Skybind authority app's **signing certificate** is not established by APK byte hashing; a separately trusted platform signer authority and direct app/package binding are required. The current BKX source/APK has not been updated; chrootctl module binary has not been rebuilt, installed or re-sealed. Android SELinux reachability for BKX/chrootctl consumer sockets and live read/grant/revoke negative receipt remain **PENDING DEVICE**. No external API advertised, production listener enabled or release qualification asserted.
- **Status:** IMPLEMENTED_SOURCE_UNQUALIFIED for new backend/handoff/operator gateway, CHROOTCTL_SOURCE_ADAPTER_ISOLATED_TESTS, BKX_REFERENCE_ONLY, SIGNER_TRUST_ANCHOR_INCOMPLETE, LIVE_ANDROID_CONSUMER_ACCEPTANCE_PENDING. Record any future Devtool/consumer limitations against this cumulative entry rather than losing them in chat.


## 2026-10-21 — R1 release-target working-directory regression (Devtool e91bf21001bf45128a760632c8710e43)

- **Evidence:** After successful application of the cross-repository R1 integration bundle, `./devtoolw r1-consumer-integration-source` launched `skybind_release.r1-consumer-integration-contract` from `skybind/release` and attempted `scripts/dev/android/r1_consumer_integration_source_gate.py` relative to that directory. The resulting missing-file error blocked the four dependent workflow nodes. This was a workflow configuration failure, not a backend/grant test failure; previous source tests did not execute from the release target working directory.
- **Root cause and secondary findings:** The new contract job omitted the parent-relative `../` used by adjacent release jobs. The new integration Go job and pre-existing consumer-transport Go job also omitted `go -C ..` and would have failed from `release/` at a later stage.
- **Repair:** Correct all three commands; include `./internal/provider` in integration Go coverage; derive the release root from parsed `.devtool.toml` and validate all three job working directories in the R1 integration source gate. Add mutation tests that regress each originally broken command. The repair uses exact SHA-256 preimages of the already applied Skybind integration overlay and does not touch chrootctl or BKX.
- **Status:** Source-level working-directory repair packaged; Termux Devtool invocation and dependent jobs **PENDING real execution**. Preserve all previously accepted PM-channel/M3 evidence, native-rclone fallback, read-only policy, default-deny listener state, and external/release-qualified=false.


## 2026-10-21 — R1 live chrootctl process qualification staged after release-CWD repair

- **Evidence and prerequisite:** The installed BKX Android-to-Go PM-channel seven-case receipt passed, but external consumer data access and chrootctl workload identity were not qualified. The cross-repo integration adds a root-only `skybind-r1-module-check` diagnostic and opt-in chrootctl adapter; historical 1.3.7 module metadata must **not** be used as a trust seal for a rebuilt binary. Skybind `main` must be pushed after the applied integration/CWD repairs before the hosted diagnostic can have matching source provenance.
- **Implementation:** Added `r1_chrootctl_process_device.py` to authenticate GitHub diagnostic run identity and both binary SHA-256 sums, preserve source equality, and optionally test an **already-running** installed chrootctl PID using separately approved manifest SHA-256 and SELinux context. Three real-device tests: correct process, incorrect module seal and incorrect SELinux context. Every receipt remains unqualified for external provider, broker grants, BKX app integration and release. Preflight-only mode does not run a root command.
- **Regression and Devtool ergonomics:** Added offline mocked-positive/negative receipt checks, corrupt artifact denial, source mismatch denial, operator-approval gate and immutable claim assertions. Added a `skybind_release` two-node `r1-chrootctl-process-source` DAG with correct `../` release target cwd, plus hosted source-only tests. No Android APK source or module service hook changed.
- **Status:** Source tools staged; hosted diagnostic run and installed chrootctl upgraded-binary seal, live process-PID acceptance and SELinux socket reachability **PENDING**. No R1 consumer grant/read/revoke device acceptance yet; no repeated M3 device tests, no backup operations, no BKX rebuild and no changes to native-rclone fallback.


## 2026-10-21 — R1 hosted consumer diagnostic: unprivileged APK fixture ownership regression

- **Evidence:** GitHub Actions run `39606948165`, source `b966b2cd921c91933cee47ba7bc9f364bdea7c3e`, `r1-consumer-gateway-source` fails `TestAuthorityAPKExactApprovedBytesAndMutation` with `android_peer_unverified` on `authority_apk_test.go:37`. Hosted runner creates the temporary fixture under an ordinary Ubuntu UID, while the real Android APK anchor correctly accepts only UID 0 or UID 1000 file ownership. No arm64 diagnostic artifact was built or uploaded; no live BKX/chrootctl qualification has changed.
- **Affected:** `internal/brokeridentity/authority_apk_test.go`, `.github/workflows/skybind-r1-consumer-diagnostics.yml`, `tests/test_r1_consumer_integration_source.py`.
- **Root cause:** Test incorrectly assumes an ordinary CI runner can create an approved root-owned APK fixture. Previous local root execution concealed the incompatibility. This is **not** evidence that the production APK ownership restriction should be weakened.
- **Repair:** Keep the production owner/type/mode and SHA-256 verifier unchanged. Under unprivileged non-system UID, assert that same-digest untrusted-owner APKs are denied with a named PASS; skip *only* the positive test requiring privileged fixture ownership. Under `sudo` on hosted CI, run the positive fixture/mutation test and explicitly require a named `PASS` line (not a `SKIP`), before running the full privileged identity/broker suites. Add a Python source regression enforcing both lanes.
- **Status:** REPAIR_SOURCE_IMPLEMENTED; hosted CI rerun and live consumer gateway/module acceptance **PENDING**. Historical seven-case Android-to-Go PM bridge PASS and four M3 independent scopes preserved. No grants, SELinux alterations, BKX/chrootctl binary changes or Android builds performed by this repair.

## R1-E2E-20261021 — Persistent Android PackageManager authority and real BKX/chrootctl clients

- **Status:** Source implementation delivered; hosted Android APK/module builds and live consumer acceptance remain PENDING_INDEPENDENT_AUTHORITY. This is not a release seal.
- **Evidence:** `PASS_R1_ANDROID_TO_GO_PM_THREE_CASES_PLUS_FOUR_AGENT_NEGATIVES` at `7ba88071f6e3446316948c4789c80d33be7963ee`; hosted R1 consumer diagnostics 39618531810 and source run 39618491599 at `4ceb62141390d98fcbdd9d827e389ff1b9f2d380`. User requested a single actual integration after numerous diagnostic-only phases. Source inspection found `MainActivity.onStop()` always killed `R1PMBridgeAgent`, making cross-app BKX PM attestation fail when Skybind left the foreground. BKX had only a non-installed Kotlin reference adapter and chrootctl's command had a short 25s approval window.
- **Affected projects:** Skybind Android app and root gateway, BKX Android `RcloneRemotesScreen`, chrootctl opt-in CLI, Devtool source-bound overlay delivery.
- **Changes:** Add explicit non-exported, non-sticky foreground `specialUse` authority service with visible stop action and reconnect attempts; preserve on-foreground automatic PM bridge behavior for historical R1 acceptance; make authority socket idle read blocking rather than disconnecting after five seconds; install a first-class BKX read-only remote/size/list/capabilities UI backed by the kernel-peer-verified grant handoff, running on a coroutine IO dispatcher with no native fallback; enforce chrootctl root process and 120-second operator wait; add source and Android argument-negative checks; ship source-verified hosted gateway launcher and explicit root-owned policy provisioner.
- **Safety:** No daemon auto-start, no automatic grants, no storage credentials or tokens persisted, no backup/Restic mutation, no silent native rclone fallback. Root gateway and policy remain explicit operator actions. BKX archived source is 2026-10-16: exact-source preflight blocks newer incompatible checkout rather than overwriting it. chrootctl's independent manifest-seal approval is required after updating its binary. Android SELinux admission must be observed on device; never broadly disable SELinux.
- **Devtool follow-up:** Add a first-class cross-repository preflight/aggregate workflow that separates source compilation, installed signing/manifest provenance, Android UI/FGS lifecycle, kernel socket reachability, real grant/read/revoke, and release qualification. Don't reuse M2/M3 device gates or convert CI-build PASS into external provider PASS.


## R1-PKG-CACHE-20261021 — Generated Python caches incorrectly inventoried in a Devtool overlay

- **Status:** Source-bound replacement packaged; Termux application and live CI pending.
- **Evidence:** Devtool run `dd03003f023a4309b56f9ccfe30b3805` failed at `artifact-check` (`artifact-validation`) before applying the Skybind R1 real-consumer connection overlay. Invalid inventory paths included `scripts/dev/android/__pycache__/r1_end_to_end_source_gate.cpython-313.pyc` and `scripts/dev/android/__pycache__/r1_operator_live.cpython-313.pyc`. The corresponding BKX overlay additionally inventoried `scripts/devtool/__pycache__/r1_skybind_source_gate.cpython-313.pyc`, which would be rejected when reached.
- **Cause:** The bundle builder used a recursive directory walk without excluding interpreter caches after source-gate validation. The validation scripts also used `python3 -B -m py_compile`, which still writes bytecode because `py_compile` explicitly requests it.
- **Affected:** Skybind and BKX R1 Devtool overlay inventories; three-repository coordinated apply script. Devtool's canonical generated-file rejection worked as intended. chrootctl overlay had no cache entry.
- **Repair:** Exclude all ignored generated cache payloads from every inventory and ZIP; replace explicit `py_compile` invocation with in-memory `compile(..., 'exec')` checks; add cross-repo archive preflight for generated paths, duplicate entries, manifest hashes, and unexpected files; retain all source preimage pins and verify outer SHA256SUMS. No device/backend/broker code changed.
- **Regression acceptance:** Reject a synthetic cache member and a synthetic duplicate inventory entry; check every embedded artifact against its inventory with zero generated paths; run the source validators without bytecode generation.
- **Qualification:** Source-bundle structural tests PASS. Real Devtool application and BKX/chrootctl hosted build/device evidence pending; original PM-channel PASS retained.


## R1-CI-SDK-001 — BKX and chrootctl hosted Android SDK v3 bootstrap regression

- **Status:** Source fix prepared in three source-bound Devtool overlays; awaiting fresh hosted GitHub Actions runs before treating CI or deployment as qualified.
- **Evidence:** BKX Actions run `39632888596` at `73cccc8866e21fc5e0e0a123767b95c3c01a82c4` and chroot-ctl run `39632895344` at `84fd16abad9b5ac53a1bcebea1c978d057d4385c` both failed in `android-actions/setup-android@v3` before compilation or artifact production. Each called the removed `sdkmanager tools` package and returned `Warning: Failed to find package 'tools'` (exit 1).
- **Working comparator:** Skybind Android build `39632874789` (commit `a706211b179762d135a9940e404f08633ce4ab0f`) passed with `android-actions/setup-android@v4`, its declared `packages` input, and `log-accepted-android-sdk-licenses: 'false'`. Skybind gateway build `39632881743` also passed.
- **Affected:** `Mikeyphw/bkx/.github/workflows/devtool-android-build.yml`, `Mikeyphw/chroot-ctl/.github/workflows/devtool-chrootctl-build.yml`. This is a cross-consumer hosted CI bootstrap failure, not evidence that native build or the real Skybind consumer integration has passed or failed.
- **Implemented repair:** Match Skybind's v4 `packages` configuration; BKX declares Android 36, build-tools 36.0.0, platform-tools, and NDK 29.0.14206865; chroot-ctl declares platform-tools and the same NDK; verify installed SDK/NDK files. Do not modify application signing, BKX APK identity, module provenance, root policy, or consumer grants.
- **Acceptance remaining:** Hosted rebuild and inspected artifact for each consumer; APK signing compatibility, installed module seal, SELinux abstract-socket connectivity, real BKX and chrootctl scoped read/grant/revoke; production and release qualification remain false until real-device evidence.


## R1-CI-GO-ONLY-002 — Consumer source gates collide with Go-only purity seals

- **Evidence / actual GitHub runs, 2026-10-21:** BKX `39637240477` at `b2d54883e8e53ea91e2c9ad82639b323716a5b58` failed `TestRepositoryPythonPurgeSeal` on `scripts/devtool/r1_skybind_source_gate.py` and `scripts/devtool_actions_contract.py`. chroot-ctl hosted `39637263876` at `6a348cb61172a976ae4a88e7b9004e0d6e5c7027` passed SDK/NDK bootstrap, then failed `repoctl validate`/`repository-purity` on `scripts/devtool/r1_skybind_live_source_gate.py`; `scripts/devtool_actions_contract.py` would also violate the same rule. Both push-CI runs (`39637240477`, `39637247938`) independently failed the still-configured `android-actions/setup-android@v3` / removed `sdkmanager tools` bootstrap (`Warning: Failed to find package 'tools'`).
- **Positive, separately qualified scope:** BKX hosted debug APK run `39637257931` passed Android/NDK setup, native generation, arm64 payload/page-size checks, package signature inspection and artifact upload `bkx-android-debug-apk` (ID `12361707814`), source `b2d54883...`. Skybind source validation `39637254187` passed, source `5d745db...`. BKX debug artifact does not establish installed signer compatibility or R1 live connectivity.
- **Root cause:** Incompatible Python-only source-contract scripts were introduced into repositories with deliberately fail-closed all-active-Python exclusion; two ordinary push/PR workflows retained SDK v3 despite the v4 hosted-build repair. Neither calls for relaxing Go-only purity or R1 operator admission.
- **Repair package (source-bound proposal):** Delete four active Python scripts across BKX and chroot-ctl, replace each repository's actions/R1 source assertions with Go-native, tested, read-only `cmd/devtoolgates` CLI and Devtool EXO jobs, run gates during regular hosted CI and reject symlink/missing/tampered source contracts. Upgrade both ordinary CI Android lanes to `setup-android@v4` with explicit SDK/NDK package and installation-verification checks. Preserve Devtool source-bound overlay guards, existing BKX native build/signing/page-size verification, chrootctl module provenance, root policy and default-deny behavior. No automatic Android build/installation or grant.
- **Status:** FIX_PREPARED_NOT_APPLIED. No new GitHub Actions on repaired commits; ordinary CI, chrootctl artifact generation, installed signer/manifest, SELinux IPC, live grant/read/revoke and external/release qualification remain OPEN. Revalidate against newly committed/pushed exact source after applying.
- **Process improvement:** Any Go-only consumer integration must run its native repository purity gate before packaging; an all-repository preflight must verify both source HEAD and every file preimage, including deletions, before the first Devtool commit. Hosted dispatch and push-CI are separate release surfaces: both require their own completion checks.


## R1-SIZE-JSON-20261021 — Live Size rejected valid upstream rclone JSON

- **Status:** Source repair implemented and focused Go regressions pending/qualified locally; new source-bound hosted gateway and independent Android R1 Size acceptance PENDING. No policy, installation, or release qualification changes.
- **Evidence:** The user completed live `system.capabilities` reads from both BKX and chroot-ctl, and BKX remote/version/list reads. Only BKX `Skybind Size` failed, while prior IPC grant flow delivered successfully. `internal/brokerruntime/metadata.go` strictly decoded the output of `rclone size --json` into just `count` and `bytes` with `DisallowUnknownFields`. Upstream `rclone/cmd/size/size.go` prints FOUR fields (`count`,`bytes`,`sizeless`,`fs`), making the real payload fail on extra keys. Synthetic runner fixtures emitted only two keys, concealing the production incompatibility.
- **Affected projects:** Skybind Go `internal/brokerruntime/metadata.go`, integration tests and hosted R1 gateway; BKX Android R1 Size UI is the visible affected consumer but its operation name and transport already match and need no app rebuild.
- **Repair:** Parse the four upstream fields using a bounded, strict, read-only typed schema; require numeric `count`/`bytes`, reject negative or impossible unknown-size counts, reject unexpected or mismatched `fs`, drop `fs` from consumer response, and optionally include positive `sizeless` to avoid overclaiming the total. Keep canonical rclone executable/config path, valid remote/path, separate PID-bound operator grant, 12-second runtime bound, and no native fallback. Add canonical upstream fixtures and malformed/wrong-scope/secret-field negatives.
- **Follow-up:** Commit/push source repair, issue a new successful `workflow_dispatch` R1 hosted diagnostics artifact at the exact new SHA, then exercise `Skybind Size` against a small folder and inspect actual JSON + grant diagnostics. Distinguish transport PASS from remote backend PASS; if the new source still fails, inspect runtime timeout/remote-specific failure without disabling SELinux.

### R1-SECURITY-BATCH-20261022 — Interactive consumer-security batch and honest evidence

- **Affected project:** Skybind R1 gateway; installed chrootctl as actual root-module consumer; BKX prior positive-path observations.
- **Evidence:** BKX and chrootctl live capabilities reached provider metadata; BKX also showed valid Size JSON. Existing root gateway exposes `approve`, `diagnostics`, `receipts`, `revoke` but lacks a reproducible, root-operated grouped negative security acceptance with machine-readable receipt. Repeating manual grant/PID/socket operations is fragile.
- **Change:** Add explicitly invoked gateway `acceptance REMOTE`, using fresh installed chrootctl processes, native handoff and consumer sockets to show approved operation, denied different-operation and different-remote requests. Exercise the same runtime grant store against attested live process identity for operation isolation, remote isolation, wrong process, missing token, revoke and TTL expiry. Distinguish live socket vs internal grant-store evidence. Persist root-only no-token JSON and optionally consolidate prior identity/transient-device receipts. Never broaden policy, change SELinux, persist tokens, mutate rclone configuration, or start the suite automatically.
- **Risk/limit:** Root operator-only diagnostic intentionally mints and then revokes/ages short-lived grants; this is *not* a general-availability runtime feature. It does not establish BKX application negative-path socket qualification, nor trusted independent external consumer/release authority. A negative client exit alone must not count PASS without successful one-time grant delivery. A pending/failed test is BLOCKED, not PASS.
- **Status:** SOURCE_IMPLEMENTED; focused Go tests/race tests and Android arm64 compile PASS, device security acceptance PENDING until an actual device JSON receipt is produced. No release-gate closure implied.

### R1-SECURITY-BATCH-20261022 source-pin correction

- **Evidence:** supplied Skybind source snapshot at `56fe4e24e1cd1839b8005d5bca0bbc0852f9b09a` contains the Size parser fix; the earlier acceptance artifact was mistakenly pinned to parent commit `5f3aa97442a8a6ed2947c4999105528ebcfa5fc9`. Original affected-file preimages match the supplied source exactly.
- **Additional defect:** the previous acceptance main.go patch replaced existing root-only `diagnostics`; revised acceptance now retains diagnostics and all existing commands.
- **Remedy/status:** fixed in the new base-bound batch acceptance overlay, validation pending on actual Android device.

## 2026-10-22 — BKX one-session real Android socket campaign (R1-BKX-LIVE)

- **Evidence gap:** existing BKX five-operation UI success was operator-reported; chrootctl 9/9 acceptance covered a distinct root module process and was insufficient to claim BKX negative socket qualification.
- **Source evidence:** Skybind `5877fba370898945b5a2b8ccc3dc532d7495ac8d`; BKX `8886dc044976a3e5217190a4b85049cfcb23619f`; real BKX `SkybindR1ReadClient.kt` and Android instrumentation source; installed BKX signer/policy remain individually authoritative.
- **Implemented fix:** one root operator `acceptance-bkx REMOTE [PATH]` runs a fixed attested app-process instrumentation, grants only individually approved operations, tests five real responses and seven real socket negative paths (missing token, wrong operation, wrong remote, traversal, same-UID wrong process, revocation, expiry), writes a separate, root-private 12-case JSON receipt and retains existing `diagnostics`, `acceptance`, `receipts` and `revoke` behavior. Source/devices stay separated by explicit qualification flags.
- **Risks and constraints:** ephemeral hosted debug signing can mismatch a currently installed BKX APK; no uninstall, data wipe, production enabling, signer bypass, SELinux weakening or automatic root grants. BKX Kotlin compile, signer compatibility and real-device execution still pending. Cross-UID and distinct-signer token replay, M2/M3, external-provider, release remain open.
- **Status:** SOURCE IMPLEMENTED; GO TESTS/RACE/ANDROID ARM64 COMPILE PASSED; BKX HOSTED/DEVICE PENDING.


## R1-BKX-LAUNCH-20261022 — Android instrumentation launched without Android runtime environment

- **Actual device evidence:** After source-bound BKX APK pair installation and operator-approved test certificate rotation, `acceptance-bkx GDDavys` produced `/data/adb/skybind/r1-bkx-acceptance/r1-bkx-3a01d598d0ce63d56f10b52e0a33ceb9.json`, state `BLOCKED`, `reason=bkx_test_process_did_not_connect`, `socket_peer_attested=false`, and no completed cases. Root-shell `pm list instrumentation` correctly enumerated `com.mikeyphw.bkx.android.test/androidx.test.runner.AndroidJUnitRunner`. Direct root-shell `am instrument -w -r` loaded `SkybindR1LiveBrokerAcceptanceTest` but failed with `Connection refused` because there was no coordinator socket (expected for this isolated diagnostic). Its terminal status was `INSTRUMENTATION_CODE: -1` **despite one JUnit failure**.
- **Cause suspected by source inspection:** Go `runBKXDeviceAcceptance` replaced the entire Android process environment with only PATH and HOME before invoking `/system/bin/am`, discarding `ANDROID_ROOT`, `ANDROID_DATA`, runtime APEX environment and classpath-related Android boot settings. This likely prevents Android's am/app_process launcher from working from the root gateway. Device proof of this cause remains pending.
- **Affected:** Skybind `cmd/skybind-r1-gateway/bkx_device_acceptance.go`, acceptance tests, hosted R1 gateway artifact; BKX installed app and test APK are not implicated by these facts and do not require rebuilding.
- **Fix:** Supply a system-only PATH/HOME, fixed Android root/data paths, and allowlisted inherited Android runtime/boot environment; never forward Termux LD_PRELOAD, LD_LIBRARY_PATH, CLASSPATH, or PATH. Observe instrumentation exiting before the socket accept timeout, label failures with sanitized fixed categories, boundedly capture stderr, never persist raw instrumentation output, and ensure the terminal JUnit success evidence includes `OK (1 test)` while rejecting `FAILURES!!!` / `INSTRUMENTATION_STATUS_CODE: -2` even when `INSTRUMENTATION_CODE: -1` appears.
- **Evidence and state:** Focused Go tests, race tests and Android arm64 gateway compile PASS locally on reconstructed current Skybind R1 sources; source-bound Devtool overlay PREPARED, not yet applied or hosted. Re-run successful GitHub `workflow_dispatch` diagnostics at new Skybind SHA and the existing root operator `acceptance-bkx` campaign. Require all 12 named socket phases, attested BKX peer, and terminal JUnit pass in a new root-private receipt before recording live-device qualification. Do not change BKX signing pin, root policy, chrootctl 9/9 receipt, device data, external provider or release claims.


## R1-BKX-HELLO-PATH-20261022 — Empty relative path omitted from test handshake; 12/12 live qualification achieved with nonempty path

- **Affected:** Skybind `cmd/skybind-r1-gateway/bkx_device_acceptance.go` and protocol tests; BKX Android's installed `SkybindR1LiveBrokerAcceptanceTest.kt` expects the coordinator handshake `path` key unconditionally.
- **Observed real device:** After repairing Android instrumentation launcher, `acceptance-bkx GDDavys` connected to the installed BKX test socket and attested its peer, but stopped before the first case: `no_token=BLOCKED/missing_or_unordered_step`, `campaign=bkx_control_or_socket_assertion_failed`, receipt `/data/adb/skybind/r1-bkx-acceptance/r1-bkx-0a57cb218868add39c4df00ba2f6d534.json`. A raw `acceptance-bkx GDDavys:ssd` was properly denied as `operator_policy_scope_not_approved` because colons aren't part of the approved remote name.
- **Root cause verified in sources:** `bkxReply.Path` used `json:"path,omitempty"`, so an authorized empty relative path produced no `path` JSON key. BKX Kotlin calls `hello.getString("path")` without an optional fallback; the missing key throws before the first ordered `prepare` frame.
- **Proven workaround and device qualification:** `acceptance-bkx GDDavys ssd` passes **all 12** independent live-socket BKX cases, including 5 positive read-only operations, no token, wrong operation/remote/path/process, revocation and expiry. Receipt `/data/adb/skybind/r1-bkx-acceptance/r1-bkx-969c677654209b852bb0e734ec7c9a77.json`: `state=PASS_R1_BKX_LIVE_SOCKET_ACCEPTANCE_ONLY`, `socket_peer_attested=true`, `instrumentation_terminal_pass=true`, `bkx_negative_socket_qualified=true`. Prior chrootctl nine-case security acceptance was independently PASS. External provider and release qualification remain false; M2/M3 retests not established by this receipt.
- **Source fix:** Drop `omitempty` **only** from the `path` field of `bkxReply`, ensuring explicit `"path":""` on the empty-prefix route. Add a Go unit regression covering empty and nonempty paths, preserving authenticated peer verification, scope rules, and 12-case terminal requirements. No APK rebuild, installed policy mutation, UID/certificate rotation, or requalification shortcut.
- **Status:** `PASS_DEVICE_WITH_NONEMPTY_PATH` for the 12-case acceptance gate; `SOURCE_FIX_COMMITTED` in Skybind `fa608ebe711296f22038dacedc94b623cb703a25`. Hosted redeployment and default-empty-path real-device rerun not established by this source change. Do not reclassify the older blocked receipts as PASS. Existing device acceptance receipt remains valid even without applying this ergonomic/protocol fix.

## R1-M2M3-FRESH-NINE-LANE-20261022 — Consolidate next two qualification windows; preserve device receipt truth

- **Scope and evidence:** BKX R1 real-device `acceptance-bkx GDDavys ssd` finished all **12/12** cases, attested installed socket peer, JUnit terminal PASS, and isolated cross-process replay; root-private receipt `r1-bkx-969c677654209b852bb0e734ec7c9a77.json`. Prior chroot-ctl root socket security **9/9** PASS. Combined read-only collector `r1-bkx-consolidated-3bf26ab28a7046208c91050b13afd3f2.json` says `PASS_R1_BKX_AND_CHROOTCTL_NARROW_LIVE_ACCEPTANCE_ONLY`, with `m2_m3_device_retests_run=false`, `external_provider_qualified=false`, `release_qualified=false`. All receipts remain immutable. The empty-path handshake repair was independently committed as Skybind fa608eb before this M2/M3 overlay; this rebase preserves that implementation and its stronger existing regression test.
- **Audit defect (existing M3 runner):** `scripts/dev/android/m2_live_device.py` implemented `m3-copy-live` and required `allow_disposable_copy_writes` internally, but argparse omitted both the mode and authorization switch. Requested COPY could never be selected from its CLI. **Implemented fix:** expose both without weakening the explicit fixture/integrity checks or historical receipts.
- **Ergonomics/performance defect:** repeated independent M2/M3 device runs reauthenticated the same GitHub workflow, hash/signature/installed app+test bytes, device API and SELinux state eight or nine times. This wasted many full-device APK pulls and manual orchestration. **Implemented fix:** `m2_m3_retest_batch.py` does exactly one admission and runs five readonly or nine explicit full cases sequentially, emits a private machine-readable case-by-case receipt, stops at first non-PASS and doesn't retain raw instrumentation stdout. Includes the independently opted-in app cold-launch test, not just eight instrumentation methods.
- **Mutation containment:** full nine-lane batch demands four separate flags: disposable CHECK, owned cancel, test-owned COPY and Skybind app-only force-stop. Fixtures must already be registered and their exact test directories/bytes/sentinel verified. No module install, daemon force-stop, implicit delete, remote mutation, root grant revision or arbitrary command. On failure no automatic cleanup and `m2_m3_device_retests_run` remains false.
- **Trust/crosswalk defect:** the R1 21-case device consolidated receipt and Q16 provider raw artifacts must not be treated as proof of later M2/M3 reruns, independent upstream origin/custody, G01 or release readiness. **Implemented:** `r1_remaining_gates.py` exact-case/schema validator with SHA256 source evidence references and immutable receipt; only a complete fresh nine-lane receipt qualifies that narrow flag; G01/provider/release false even with a valid Q16 raw two-lane summary. External producer provenance still needs independent authority.
- **Empty-path handshake:** Go `bkxReply.Path` used `omitempty` while Kotlin uses `getString("path")`, causing `acceptance-bkx GDDavys` to die before first `prepare` despite attested process; `acceptance-bkx GDDavys ssd` passed all cases. One-line Go wire fix and empty/nonempty regression already present in source base fa608eb; unchanged by this overlay. No requalification claim for default empty path until actual new gateway run.
- **Implementation/source proof:** new Python batch unit negatives (profile authorization, no early qualification, terminal contradictions, fixture state, first-failure stop), crosswalk negatives (missing cases, unapproved Q16 escalation) and existing M2/M3 suites, focused Go tests and Android arm64 build. See `docs/devtool/SKYBIND_R1_M2_M3_DEVICE_RETEST_AND_PROVIDER_CROSSWALK_20261022.md`.
- **Status:** `SOURCE_IMPLEMENTED_LOCAL_TESTED` on source-bound Skybind base `fa608ebe711296f22038dacedc94b623cb703a25`; apply/hosted APK device re-test/publisher custody gates **OPEN**. Do not mark this as G01, external-provider or release PASS.

## R1-M2M3-REBASE-20261022 — Source guard failure and non-destructive merge

- **Evidence:** Original wrapper hardcoded HEAD `3e9715fb1718a324336c3d7ff3a854487237c560`, whereas provided clean snapshot has `fa608ebe711296f22038dacedc94b623cb703a25` and exactly one intervening BKX empty-path commit. The M2/M3 overlay refused with `BLOCKED_M2M3_WRONG_SOURCE_COMMIT`; no user-source mutation occurred.
- **Resolution:** Rebase overlay and SHA256 preimages to fa608eb; OMIT already applied Go path fix and its test from overlay rather than reverting stronger current test. Preserve all existing ledger entries; apply only missing M2/M3 CLI exposure, automated batch, source-only tests, crosswalk, docs and cumulative ledger.
- **Qualification:** Snapshot clean, source preimages checked. Local simulation and regression/Devtool validation reported separately; 21 historical R1 device security cases retain their prior receipts. M2/M3 fresh device execution, independent upstream/builder custody and release gates remain OPEN.


### 2026-10-22 — M2 L2 Jobs/Activity scroll and diagnostic granularity (NEXT-L2-01)

- **Affected:** Skybind Android `LiveUiAcceptanceTest` (M2 L2 Compose read-only UI), the source guard, device failure classifier, and batch receipt. The installed source-bound app/test pair came from successful workflow run `39806261993`, source `c9c45b10a1e9ca592b0e1b24a599e778c6ccc957`.
- **Observed device evidence:** `ci_artifacts_device.py` returned `PASS_CI_PAIR_VERIFIED_NO_TESTS_SELECTED` with installed pair matched. Five-lane `m2_m3_retest_batch.py` passed `live` then failed `ui-live` at `SKYBIND_UI_FAILED_JOBS_ACTIVITY`; receipt `~/.local/state/skybind/m2-m3-retests/m2m3-8be4b14d5a744094bfd911ebafbb8140.json` reported one PASS and stopped before remaining lanes. This is not a five-lane PASS, and does not affect BKX 12/12 or chroot-ctl 9/9 receipts.
- **Source audit:** The legacy test wraps four Jobs/Activity interactions in one failure marker; `jobs-view-activity` and `activity-view-jobs` are rendered below potentially lengthy real daemon lists in a scrollable Compose `Page`, but the test uses `performClick()` without `performScrollTo()`. A precise runtime stack trace was not retained, so offscreen interaction is a plausible defect, **not yet an independently confirmed explanation** for this particular device failure.
- **Remediation prepared:** Scroll both bottom-of-page navigation controls and the filter before interaction; split the four phases into separate fixed failure markers while retaining no-cross-screen-data assertions, explicit opt-in, real UI and authenticated daemon, and legacy failure-marker parsing. Update the source-contract gate and negative regression tests together. No production UI, daemon, BKX, root trust policy, installed signing keys, or previous evidence altered by this source patch.
- **Qualification:** Source and Python regression tests can pass locally; Android instrumentation compilation and fresh on-device L2 testing remain required. Rebuild the exact-source hosted APKs, admit compatible app/test signatures without uninstall/data-clear, rerun the read-only batch; keep M2/M3 overall and Q16/G01 release qualification OPEN until independent evidence passes.


### 2026-10-22 — M3 fixture source/target divergence and host-only APK source admission
- **Affected project:** Skybind M2/M3 Android acceptance and Devtool overlays; real target `emulator-5554`.
- **Observed:** Exact GitHub hosted APK pair `39821151117` (source `d9f275f06f0c986d867d6c7173d0e5fad21ff9a5`) verified and installed; M2 L1, M2 L2, M2 L3 negative and transport all PASS. M3 read-only preview BLOCKED `SKYBIND_M3_BLOCKED_NO_ELIGIBLE_JOB`, with four of five batch lanes PASS and valid blocked receipt `m2m3-452fa6db6f3d41e581ca2c024c079cad.json`.
- **Root cause:** Installed instrumentation selects an enabled CHECK/COPY daemon job, and none is configured. Existing `m3_disposable_fixture.py`/`m3_copy_fixture.py` always operate on local Termux paths and `su`, while the batch specifically targets an ADB serial; applying them unmodified may mutate a different daemon. Independent same-serial targeting is mandatory.
- **Implemented:** Exact target ADB fixture helper for root jobs.status/preview/apply with explicit apply; bounded test-owned CHECK/COPY file payloads and device-side SHA-256/membership/symlink verification; batch full-profile fixture preflight and post-COPY integrity use the same admitted ADB serial. No fixture is created by the test runner; no job started by the fixture helper; no SYNC registry allowed.
- **Source compatibility:** Host tooling-only follow-up commits cannot claim a hosted APK of the new commit. Add explicit `--apk-source-sha` pin and review the intervening Git diff, restricting it to the exact fixture/runner/test/ledger files with no Android or workflow change, still attesting the originally hosted APK source and both APK hashes. Default source-match admission unchanged and fail-closed.
- **State:** Prepared/locally regression tested, not yet installed or proven on device. The earlier 21/21 BKX/chrootctl R1 security evidence remains closed. Fresh five- and nine-lane M2/M3 device qualifications are OPEN. Provider origin and release gates remain OPEN.


### 2026-10-22 — M3 ADB fixture root transport and diagnostics (NEXT-M3-02)
- **Evidence:** Source-bound APK build run `39835482344` at `ba0b718a3ff42b8646c546e1fbd81fabe0d655e4`, emulator serial `emulator-5554`. M2 L1/L2/L3-negative/L3-transport four lanes PASS. Fixture `prepare-check --apply` reports `TARGET_ADB_COMMAND_FAILED` without an exit, stage or cause; M3 preview reports `SKYBIND_M3_BLOCKED_NO_ELIGIBLE_JOB`. Batch receipt `m2m3-87d86cd05e624c468a9470f11b7d48c2.json` correctly records four PASS and M3 blocked, never five-pass qualification.
- **Defect:** `m3_adb_fixture.py` runs `adb shell su -c <command>` as separate arguments (Android remote shell argv may break quoted JSON); assumes `su` availability even if emulator adbd already runs as UID 0, and collapses all failing ADB commands to the identical `TARGET_ADB_COMMAND_FAILED` marker.
- **Repair:** Check selected target serial and fingerprint, probe `su -c id -u` first then accept already-root adbd only when the shell itself proves UID 0; no `adb root`. Quote the complete root command as a single remote shell string. Preserve fixed-operation allowlist and fixture path/hash/symlink membership checks, explicit `--apply`, and root authority. Stage-specific nonsecret category, exit and stdout/stderr byte counts on command failure; never echo raw registry/tokens or enable mutation during diagnostics. Add targeted positive/negative Python tests.
- **Status:** `SOURCE_REPAIR_PREPARED`, local tests PASS. Exact-commit Devtool application, hosted CI and real-device root/fixture admission still must be observed. Preserve the historical four M2 PASS and 21/21 R1 security receipts; full M2/M3, independent external provider and release gates remain OPEN.


### 2026-10-22 — M3 same-ADB-device SHA transport and recovery (NEXT-M3-ADB-HASH)

- **Affected:** Skybind `scripts/dev/android/m3_adb_fixture.py` selected-device CHECK/COPY fixture staging and M2/M3 Android qualification runner; emulator `emulator-5554`.
- **Device evidence:** `PASS_TARGET_M3_FIXTURE_INSPECTION_ONLY`, registry revision 6, no verified fixtures; explicit `prepare-check --files 512 --apply` blocked at `FIXTURE_SHA256_VERIFICATION exit=1 category=UNCLASSIFIED stdout_bytes=0 stderr_bytes=13`, after ADB root selection and fixture staging. Four M2 lanes PASS; M3 preview BLOCKED `SKYBIND_M3_BLOCKED_NO_ELIGIBLE_JOB`; the original blocked receipts stay retained, not falsely qualified.
- **Root cause and limitation:** Old fixture verifier placed all 1025 CHECK file paths into one Android shell `sha256sum` invocation, exceeding conservative command transport limits. Failure reason was masked by category-only diagnostics, so exact OS error unconfirmed; no assumption that the staged data were invalid.
- **Implementation:** Exactly 16 generated paths per command, no more than 4096 UTF-8 bytes, ordinal `FIXTURE_SHA256_BATCH_NNN` stage; complete device membership and symlink checks precede hashing; every digest/path must match the independently generated expected set, duplicates/missing lines are denied. If a previous push left a fixture directory without registry entry, verify its complete on-device contents before adopting it; never overwrite, delete, or register a partial/conflicting directory.
- **Proof:** 16 focused Python source regressions including 512 CHECK pairs/1025 hashes, wrong digest, unexpected paths, missing/duplicate rows, numbered transport failure, exact staged adoption, and no jobs.apply after verify failure. Devtool source-bound validation remains mandatory.
- **Qualification:** Actual root ADB fixture preparation on `emulator-5554` still OPEN until success receipt. Then rerun M3 read-only preview/full nine lanes with selected serial and exact hosted APK admission. Prior BKX 12/12 + chrootctl 9/9 remain closed; external provider/release gates remain OPEN.

### 2026-10-22 — Personal release authority migration (PERSONAL-V1)
- **Evidence:** The source ledger records BKX 12/12 and chroot-ctl 9/9 narrow R1 security successes, Q16/Q17 first-party evidence, and M2 read-only passes. The latest M2/M3 entry still records M3 as blocked and no demonstrated fresh full nine-lane PASS; personal policy requires an independently valid first-party nine-lane receipt before approval. Original G01–G08/CFS1 external-signature design caused all eight gates to stay BLOCKED despite this being a personal project.
- **Change:** Canonical SB-G01/G02/G03–G08 and CFS1 entrypoints now report `SKYBIND_PERSONAL_V1` local evidence and owner-accepted, candidate-hash-bound release status; third-party signer, builder custody and whole four-manager device matrix are not active prerequisites. Devtool personal builds remain source/toolchain/ZIP/ELF verified. Existing Q16/Q17/R1/M2M3 evidence is revalidated against reviewed source content and source lock. New private evidence index and explicit owner approval are outside Git.
- **Truthful scope:** Manual UI/device verification is explicitly owner reported and never called independently attested. Untested devices/managers remain outside scope. A clean checkout, frozen source/catalog, correct evidence hashes, verified candidate ZIP and owner authorization still required. No automatic module install or data mutation during audit.
- **Affected:** Skybind qualification and gate adapters, CFS1 personal authority, Devtool readiness commands, personal export metadata, owner documentation and regression tests.
- **Status:** SOURCE_OVERLAY_PREPARED, subject to Devtool installation and actual evidence checks. The nine-lane M2/M3 receipt, if not yet available, is an outstanding owner evidence prerequisite alongside device/UI review and exact candidate approval. No runtime/module modifications or Android APK rebuild introduced by the policy itself.


### 2026-10-23 — PERSONAL release local Go 1.27.3 exception (HOTFIX-GO-1273)
- **Observed:** `./devtoolw personal-release` blocked before Q04 provider download/compilation at `scripts/dev/integration/local_build.py:selected_go`: Termux `go1.27.3` versus immutable CI pin Go 1.27.2 and sole older local exception 1.27.1. Actual Devtool run `d08115282ba346b09eca8e9cf98ef5d7`, failure `SKYBIND_PERSONAL_BLOCKED`. All first-party personal evidence gates G01/G02/G05/G06 previously registered PASS; owner approval remains outstanding.
- **Cause:** Explicit version allowlist did not cover the installed newer patch toolchain; this is a local compiler availability/compatibility issue, not a failure of Android 9/9 or provider provenance.
- **Source repair:** Add precisely local-only Go 1.27.3 to the Go 1.27.2 compatibility exceptions, retaining original Go 1.27.1 and exact pinned Go 1.27.2; improve allowed-version error output. Preserve `GOTOOLCHAIN=local`, source lock, CI workflow Go selection, upstream Q04 evidence pins, fail-closed ELF `go version -m` check and receipt metadata that identifies actual Go 1.27.3 as `NOT_ATTESTED_NOT_CI_EQUIVALENT`. No formal G01/CFS1 promotion.
- **Tests:** New Python regression covers accepted Go 1.27.1/1.27.2/1.27.3, rejected 1.27.0/1.27.4/1.28.0, different CI pin, compiler environment, exact receipt fields and negative receipt rejection. Source-bound Devtool validation is required.
- **Status:** SOURCE_HOTFIX_PREPARED; local Python regression is not a substitute for real Termux `go1.27.3` Go vet/test/cross-compile and personal candidate verification. Once Devtool applied and source committed, rerun personal evidence check (historical product-unchanged receipts remain conditionally valid) and personal build, then explicit owner UI/device approval.


## NATIVE-00/01 foundation (2026-10-23, implementation candidate)

- **P0 qualification correctness:** personal_policy.product_compatible formerly compared selected runtime paths but omitted `android-app/`. Implemented conservative allowed-tooling-path classifier; Android, AIDL, resources, CI and unknown diffs cannot reuse historical personal M2/M3 evidence. Unit negative coverage still required for approval; previous owner approval stays bound to historical source. **Status:** source candidate, needs Devtool and device acceptance.
- **P1 native UX:** built foreground root auto-connect (one initial attempt, one bounded binder-loss reconnect; root-manager approval never bypassed), direct Mounts tab, daemon-verified per-mount query, source read allowlist, safe status display and compact lazy browser. **Status:** source candidate, new Android build and device instrumentation pending.
- **P1 branding:** launcher label Skybind, original editable S-connection SVG and Android adaptive/themed/legacy icon resources, status bar/header correction and isolated BKX foreground authority settings. **Status:** source candidate, visual/device acceptance pending.
- **P1 source-contract debt:** updated legacy source tests to verify the new auto-connect contract rather than permanent manual click; feature parity writes remain intentionally blocked until proof-bound lifecycle overlay. **Status:** source candidate; tests/CI pending.
- **Affected projects:** Skybind native app, Devtool CI source gates; no changes to BKX or chrootctl.

## 2026-10-23 — Skybind NATIVE-02 authenticated mount lifecycle (source-only)

**Projects:** Skybind native Android app, root Binder bridge, Skybind daemon mount lifecycle, Devtool overlay/qualification. **Status:** SOURCE IMPLEMENTED; ANDROID BUILD / TEST / OWNER APPROVAL OPEN.

**Evidence and limitation:** The applied NATIVE-00/01 foundation has authoritative `mount.status`, but Android exposes no mount lifecycle controls. The daemon already implements `mount.start.preview`/`mount.start` with one-use configuration revision proof and `mount.stop`, `mount.restart`, `mount.reconcile` without equivalent daemon-issued previews. Prior native M1/M2 source gates forbid every mount write, making the legitimate new scope fail even when narrowly authenticated. These guards require contract evolution, not deletion.

**Changes:** NATIVE-02 adds four separate AIDL preview entry points (Start/Stop/Restart/Reconcile) plus a one-shot confirm. `RootReadBridgeService.kt` pins caller UID/package and daemon UID/socket, validates configured name/revision and observed mount status, hides start proofs from the UI, issues short-lived session-bound consumed tickets and rejects replay, foreign sessions, stale revision/identity and unknown operations. It preserves daemon FUSE ownership checks and requires an explicit checkbox confirmation for every action. The UI refreshes authoritative mount state after successful submission and warns against retrying ambiguous outcomes. Config create/edit/delete, generic RPC and automatic mount writes remain excluded.

**Scope limit:** Stop/Restart/Reconcile have a 60-second root-service one-time confirmation ticket and fresh daemon preflight, **not** an end-to-end daemon-issued single-use mutation proof. Root-to-daemon races and transport ambiguity must be tested on real devices and should be considered a follow-up backend hardening opportunity before labeling the mount-mutation lane fully qualified. Daemon policy, mounted-file writeback and externally owned FUSE safety remain authoritative; this overlay does not forge receipt success.

**Source tests:** 79 Android/native Python source-contract tests pass (including failure-oriented ticket/session/revision/UI regressions); `go test ./internal/mounts/lifecycle ./internal/mounts/supervisor ./internal/previewproof` passes on Go 1.23.2; legacy M1/M2/M3 source gates pass. **Unrun:** hosted Gradle app/AndroidTest compilation, API-36 instrumented tests, real test-owned Start/Stop/Restart/Reconcile, kill/reconnect and negative security acceptance, personal APK release. Old nine-lane APK acceptance remains invalid for the modified Android source.

**Recommended next changes:** (1) native lifecycle Android instrumentation with disposable mounts and rejection evidence; (2) expand daemon-issued proof semantics to stop/restart/reconcile if needed for full cryptographic action binding; (3) NATIVE-03 typed config editor with fresh revision/proof, kept separate from this overlay; (4) NATIVE-05 signed personal APK production lane. No release approval is claimed.

## 2026-10-23 — Skybind NATIVE-03 typed mount configuration editor

- **Affected projects:** Skybind Android app (`android-app`), root-owned Binder service, existing daemon config registry, Devtool source gates, and personal APK qualification.
- **Evidence:** NATIVE-02 supplies explicit mount lifecycle tickets and an authoritative `config.snapshot`, but Add/Edit/Delete remained WebUI-only. Existing static source contracts explicitly prohibited `config.apply` everywhere, so they would reject a legitimate narrow expansion.
- **Implementation:** Three distinct typed Binder previews (Create/Edit/Delete), exact-schema typed drafts, live daemon provider inventory, `config.validate`/`config.preview`/`config.apply`, root-held one-use revision-bound proof/ticket (60 seconds), caller/session/replay bounds, preserved unedited registry entries, consumed-before-I/O semantics, authentic post-write revision check. Native four-step Source → Destination → Behavior → Review editor; advanced cache, network, battery and VFS fields; explicit delete confirmation; automatic source status reload only after confirmed write. No arbitrary RPC selector/shell, credentials, generic JSON patches, rollback bypass, unattended config mutation, or auto-mount on app startup.
- **Tests:** NATIVE-03 static negative tests for foreign session, ticket reuse, stale revision, unbounded Binder method, proof leak, query-write mutation and missing UI consent. Legacy native source gates adapted to keep Browser query-only and existing job/Mount lifecycle boundaries. Existing config Go tests verify backend atomic publication and rollback. Android UI/instrumentation source tests added but hosted device execution is not yet evidence.
- **Limitations:** Daemon errors are not yet mapped to structured per-field Android diagnostics; the UI shows generic validation failures. Native editor supports at most 64 mounts and preserves all 21 public mount configuration fields; larger registries must use the WebUI. No secret-writing flows or user-controlled rollback action. No successful hosted APK compile, live create/edit/delete, writeback-busy/device-race test or personal APK sign-off has yet been demonstrated. NATIVE-02 lifecycle stop/restart/reconcile still lack daemon-issued proofs.
- **Status:** SOURCE_CANDIDATE; build/device qualification OPEN. Historical M2/M3 Android receipts and the earlier personal module ZIP owner approval must not qualify this new Android APK.


## 2026-10-23 — NATIVE-03 complete-delivery fold-in (supersedes prior partial package)

- **Issue:** First NATIVE-03 draft omitted native rollback UI and daemon-to-field structured diagnostics despite explicit feature promises; creating a release-bound overlay with those omissions would require a second installation and misstate acceptance.
- **Correction:** This replacement NATIVE-03 overlay implements typed create/edit/delete, field-specific validation codes in the daemon `config.validate` fault, strict target-field filtering in the root bridge, local field guidance, full-registry rollback preview/confirm UI using daemon proof and single-use root ticket, and an explicitly opt-in disposable live Android instrumentation test with cleanup.
- **Affected:** `internal/mounts/config`, `internal/control`, `internal/protocol`, `internal/daemon` tests; `android-app/` AIDL/service/session/UI/model/tests; native source gates and this ledger.
- **Validation evidence:** Full `go test ./...` PASS; native Python source/negative tests PASS; actual Gradle APK build/device integration still unexecuted and never claimed as pass.
- **Qualification impact:** Changes to shipped daemon and Android app require rebuilding/retesting module + APK, fresh compatible evidence, and new personal approval. Existing approved build remains separate and valid only for its exact original bytes.
- **Status:** Feature/source promises DELIVERED. Remote hosted Android compilation and real-device acceptance OPEN (external qualification gates), not simulated or silently waived.


## 2026-10-23 — Skybind NATIVE-04 personal app polish (source delivered; device gate open)

- **N04-HOME-TRUTH [source delivered]** — Native Home previously treated authenticated Binder status and mount counts as generic service health. Introduced independently validated `runtime.status` on-disk integrity, daemon mount status plus optional supervisor retry fields, and explicitly labeled Android-only network state. Files: `LiveReadSnapshotReader.kt`, `SkybindReadModel.kt`, `SkybindApp.kt`, `RootReadBridgeService.kt`. Negative tests reject forged runtime readiness and mismatched mount-health identity. Runtime readiness never asserts real FUSE or provider connectivity.
- **N04-JOBS-ACTIVITY [source delivered]** — Previously jobs and activity were eagerly composed inside a single LazyColumn item, exposed raw bytes/timestamps, and had no readable receipt detail. Dedicated keyed lazy rows, byte/time formatters, severity filters, receipt expansion, and journal-gap messaging implemented. Files: `SkybindApp.kt`, `NativePresentation.kt`, `NativePolishUiTest.kt`.
- **N04-BKX-TRUTH [source delivered]** — Existing foreground-service observation alone was optimistic. Distinguish Off, Starting, Failed, Service active/waiting for peer, and Service+peer connection; notification visibility checked separately. Does not infer BKX signer grants from socket presence. BKX remains opt-in; auto-root does not start the foreground service. Files: `MainActivity.kt`, `R1PMBridgeAgent.kt`, `R1AuthorityService.kt`, `SkybindApp.kt`.
- **N04-DIAGNOSTICS [source delivered]** — Added APK version/code, Android API, SHA-256 local installed signer reveal, runtime provider/integrity, mount health, device network and privacy wording. Module version remains explicitly unavailable because the daemon has no authenticated version field. No raw credentials nor arbitrary root query APIs added. Files: `NativePresentation.kt`, `SkybindApp.kt`, Android manifest (only normal `ACCESS_NETWORK_STATE`).
- **N04-ACCESSIBILITY [source delivered; device verification pending]** — Hoisted Browser lazy list scroll over tab recreation; stable entry keys; 48dp key controls, linear single-column mount/quick actions, tab semantics, offline/empty states, font-scaling and screenshot/semantics instrumentation fixtures. Files: `SkybindApp.kt`, `NativePolishUiTest.kt`.
- **N04-REGRESSION-GATES [source tested; Android build/device open]** — `native04_polish_gate.py` with fail-closed negative tests and existing M1/M2/M3/NATIVE-01/02/03 suites. CI compilation, screenshot capture on-device, personal APK provenance and root/device qualification are external checks; do not mark PASS until receipts exist. Existing personal module release approval remains bound to its earlier exact bytes.

## 2026-10-23 — NATIVE-05 personal signed APK pipeline (source implementation)

- **Observed gap / affected projects:** Skybind `android-app`, GitHub Android workflow, Devtool APK consumer tooling. Existing hosted pipeline built only persistent-*debug* APKs, fixed versionCode 1, and no separate non-debuggable personal APK with source/permission/capability/signer provenance or safe upgrade preflight. New NATIVE-01..04 Android source cannot be treated as accepted by the previously approved personal *module* ZIP or historical nine-lane evidence.
- **Implemented solution:** Dedicated gated `skybind-personal-apk.yml` dispatcher on `main`, explicit monotonic versionCode, non-debuggable `personal` variant and matching instrumentation variant, reuse of exact existing persistent signing key to preserve upgrade continuity, no fallback; binary `aapt` and `apksigner` manifest verification plus strict compiled permissions, rooted AIDL/service source digests, and GitHub run/source/toolchain/sha provenance. New download/verification and opt-in `adb install -r` route rejects different signing cert, downgrade, partial installed pair, mismatched bytes and unreviewed deletion; post-install APK pull confirms exact bytes. Launcher string resource, dedicated white vector notification icon and current SVG-adaptive assets kept synchronized.
- **Security/negative coverage:** `tests/test_native05_personal_apk.py`, `scripts/dev/android/native05_personal_apk_gate.py`. Fail closed on missing signing pin, bad hosted GitHub run identity, wrong AndroidTest target, permission escalation, debuggable app, replayed/unqualified manifest, installed signer drift, install without explicit flag and version rollback. It is not independently attested.
- **Qualification & status:** SOURCE DELIVERED. GitHub Android compilation/signing, API 36 device execution, installed upgrade and separate APK owner approval remain OPEN as NATIVE-06 evidence gates. Do not amend the historical personal module approval. No Devtool engine defect identified in this stage; preserve ledger entry until operational qualification.

## 2026-10-23 — NATIVE-06 native personal release evidence integration

- **Issue / evidence:** NATIVE-05 source pipeline is locally applied but the dedicated `skybind-personal-apk.yml` was not present on GitHub's default branch when checked. Old M2/M3 9-lane debug receipts must not qualify changed personal APK bytes. NATIVE-03 also changed daemon behavior, so verifying only the APK without installed daemon provenance could produce a misleading pass. Relevant previous review: `docs/qualification/NATIVE_05_PERSONAL_APK_ACCEPTANCE.md`.
- **Affected projects:** Skybind Android client (`android-app`), personal APK GitHub workflow, installed daemon/module, real-device qualification (`scripts/dev/android`), cumulative Devtool acceptance/evidence safety.
- **Delivered source change:** `native06_personal_acceptance.py` exact hosted/source/signing/installed-pair checks, module ZIP and installed daemon-binary SHA binding, explicit full/readonly lanes, skip/failure rejection, immutable on-device test receipts and owner approval/check. `NativePersonalLiveTest.kt` exercises automatic root binding and disposable mount Start/Restart/Stop/Reconcile without arbitrary shell; tests include negative receipt/consent checks.
- **Status:** SOURCE DELIVERED. GitHub workflow dispatch, real compiled AndroidTest app, root manager grant/denial, live mutation, UI review and personal APK approval PENDING INDEPENDENT EXECUTION. Do not promote old receipts. No other manager certified.
- **General Devtool improvement:** expose task workflow dispatch/source-postpush/retrieval and exact Android app/module pairing as native evidence nodes rather than expecting manual shell alignment; do not equate Devtool overlay success with external release qualification. OPEN enhancement.


## 2026-10-23 — Skybind NATIVE-00–06 deep source audit and NATIVE-06 evidence reliability fixes

- **Evidence:** audited clean snapshot `skybind-20261023-211330-315069.tar.gz`, source HEAD `02bf99fb47a5fa7c8509aa672f0438142123a621`. Existing NATIVE-06 runner generated a nonexistent mountpoint that contradicts `internal/mounts/lifecycle/engine.go::verifyDestination`; installed module digest could match while running daemon image remained stale; instrumentation receipts stored unverified digest strings with no durable log; initial auto-connect would not recover certain background transport disconnects; edge-to-edge Compose header lacked a status-bar inset.
- **Affected paths/projects:** Skybind Android Compose UI and bridge, rooted module and acceptance instrumentation harness, personal APK release qualification, Devtool source-bound handoffs; no claimed changes to unrelated BKX/chrootctl providers.
- **P0 fix:** explicit unique empty mountpoint staging + collision detection + non-destructive `rmdir` on completion; live running Skybind daemon `/proc/<pid>/exe` hash and PID validation; strict private instrumentation log bytes + digest + method/outcome reread during owner approval and approval recheck. Old unbound NATIVE-06 receipt schema is rejected.
- **P1 fix:** Android status-bar-safe header, authenticated-background-loss foreground reconnect only (no denied-root prompt loop), Android16 arm64 acceptance preflight.
- **Test evidence:** new negative regression tests for missing fixture/collision/cleanup, stale live daemon, altered/unprotected/synthetic log, old receipt, Android target, and source-shape gate. Go suite + targeted Python source suite re-run during overlay validation; no hosted compilation/device qualification is claimed.
- **Status:** SOURCE HOTFIX IMPLEMENTED / LIVE HOSTED AND DEVICE GATES OPEN. Full cross-phase promised-behavior matrix at `docs/qualification/NATIVE_00_06_DEEP_PROMISE_AUDIT_20261023.md`; NATIVE-06 operator workflow at `docs/qualification/NATIVE_06_DEEP_AUDIT_HOTFIX_ACCEPTANCE.md`. Owner's old personal module artifact retains its historical, narrower approval.
- **Future Devtool improvement:** add an automated *runtime-process binary equivalence* and *durable raw instrumentation evidence* capability to release gate contracts, plus device fixture preparation checks for daemon constraints; keep source/CI/device/owner claims separate and fail closed.


### 2026-10-23 — NATIVE-05 hosted personal APK Kotlin accessor collision (FIXED SOURCE; HOSTED REBUILD PENDING)
- **Evidence:** GitHub Actions personal APK run [40046033979](https://github.com/Mikeyphw/skybind/actions/runs/40046033979), source `85f1007f4c720ad10fb645f7cd9ca676bda2b772`, failed in `:app:compilePersonalKotlin` with two JVM signature collisions (`setBkxKeepBackground(Z)V` and `setAutoConnectEnabled(Z)V`). Signing and SDK setup passed; no APK candidate or on-device gate ran.
- **Affected source:** `android-app/app/src/main/java/io/github/mikeyphw/skybind/MainActivity.kt`, `.../bridge/SkybindSessionViewModel.kt`, `.github/workflows/skybind-source.yml`; not a Devtool transaction failure.
- **Remediation:** Rename the two *explicit* preference handlers to `updateBkxBackgroundPreference` and `updateAutoConnectPreference`, preserving property/state, saved preferences, auto-root and BKX behavior. Add `native_kotlin_setter_gate.py` with rejection tests for the original collisions, execute it in the existing source CI, and retain hosted Gradle compilation as the decisive gate.
- **Qualification:** Source guard and regressions PASS locally; personal APK compilation, instrumentation, signed APK provenance and device qualification remain **PENDING** until a new GitHub run succeeds. The failed run never created a signed personal candidate. Existing module evidence is unaffected.
- **Backlog learning:** Prefer an actual Kotlin compile gate before release qualification for future native changes, since pure source-contract tests cannot prove JVM signature compatibility. Status: source guard fixed; hosted APK build validation OPEN.


### 2026-10-23 — NATIVE-05 personal APK AndroidTest unresolved Compose imports (source fixed; hosted build pending)
- **Evidence:** [GitHub Actions run 40051717952](https://github.com/Mikeyphw/skybind/actions/runs/40051717952) on source `7366223ab386babbbcc76747d765c98522ff6097` reached and passed `:app:compilePersonalKotlin` and `:app:compilePersonalJavaWithJavac` after previous setter repair, but failed `:app:compilePersonalAndroidTestKotlin`. Three compiler diagnostics: unresolved `androidx.compose.ui.test.assertExists` in `NativePersonalLiveTest.kt:6`; unresolved `assertExists` and `assertDoesNotExist` in `NativePolishUiTest.kt:3–4`. These are member methods of `SemanticsNodeInteraction`, not top-level functions to import.
- **Impact:** Personal app/test pair not packaged or published, so no APK candidate and no on-device qualification; signed personal module approval unaffected. Source-only tests missed imported nonexistent top-level functions. No root grant or daemon mount malfunction is demonstrated by this failure.
- **Remediation:** Delete exactly three bad imports while retaining existing `.assertExists()` / `.assertDoesNotExist()` calls, extend `native_kotlin_setter_gate.py` to scan ALL AndroidTest Kotlin source for those imports, add adversarial source tests, keep the existing CI source guard wired; mark `android_test_compiled:false` in source receipts. No product functionality, privilege boundary, or package signing changes.
- **Status:** SOURCE REPAIRED; actual GitHub `assemblePersonalAndroidTest`, signed pair, device instrumentation, and final APK owner qualification remain OPEN. Upgrade CI by requiring hosted AndroidTest compilation before approving native release artifacts; static checking is supplementary, not equivalent.


### 2026-10-23 — NATIVE-05 hosted APK aapt metadata identity parser (source hotfix; rerun required)
- **Evidence:** personal workflow [40054250297](https://github.com/Mikeyphw/skybind/actions/runs/40054250297), source `9906965436e1899a41a151f1e3ab4c74079173b8`, passed production **and AndroidTest compilation** but the `personal_apk.py create` candidate verifier returned `COMPILED_PACKAGE_IDENTITY_UNAVAILABLE`. The artifact upload did not execute. No APK candidate or device receipt exists for this run.
- **Root cause / confidence:** `BADGING_PACKAGE` required a non-empty `versionName` immediately after `versionCode`. Android Gradle's generated instrumentation/test APK can have an empty or absent `versionName` even when package name and versionCode are valid. The workflow did not preserve `aapt dump badging` output or APK bytes, so the exact emitted line is not available; this is the identified brittle parser contract and a strong probable explanation, not a claim of observed test APK bytes.
- **Affected projects:** Skybind hosted Android personal pipeline (`scripts/dev/android/personal_apk.py`), NATIVE-05 verifier source gate and Python tests; not root-manager behavior, module binary, APK signing identity or Devtool engine.
- **Repair:** independently parse a single compiled `package:` line, require valid package name and numeric versionCode, reject duplicate identity attributes, accept optional/empty AndroidTest versionName, **continue requiring exact non-debuggable personal app versionName**, signing certificate, test instrumentation target, binary permissions, SDK pins, source and hash identity. Add representative mock aapt dumps, malformed duplicates and negative identity checks; update source gate. Never replace missing data with a guessed package name or versionCode.
- **Qualification:** source tests pass; actual hosted APK verifier and artifact publication must be repeated on the post-hotfix SHA. Full Android/device tests, daemon/APK equivalence, owner review and distinct personal APK approval remain open. Keep earlier approved personal module untouched. Recommendation for general release tools: capture sanitized aapt metadata or classify APK role on parser failure without leaking signer secrets. Source implementation pending external acceptance.


### 2026-10-24 — Skybind AndroidTest binary manifest metadata recovery (NATIVE-05)
- **Evidence:** GitHub personal APK run `40055856085`, source `f08cdf6134bf9efe0dac205f169ecf4c28fc9a08`, production+test APK compilation succeeded; `COMPILED_PACKAGE_IDENTITY_UNAVAILABLE:app-personal-androidTest.apk` stopped publication, no candidate/approval.
- **Root cause category:** Generated AndroidTest badging metadata not accepted by the package identity parser; exact badging not preserved, so format details remain unproven. Earlier empty versionName fallback alone failed.
- **Affected:** `scripts/dev/android/personal_apk.py`, GitHub personal APK workflow, source gate/tests; Devtool actor source-bound verification.
- **Recommendation / applied source change:** Decode manifest identity via strict alternate `aapt dump xmltree` on failed badging, accept explicit AndroidTest versionCode=0 without touching personal app version policy, reject identity drift, record public bounded metadata on verifier failure. Preserve strict signing, source, permission and instrumentation target gates.
- **Status:** IMPLEMENTED_SOURCE_TESTED; LIVE_HOSTED_REBUILD_OPEN, APK_PUBLISH_OPEN, DEVICE_ACCEPTANCE_OPEN. Reference `docs/qualification/NATIVE_05_BINARY_MANIFEST_IDENTITY_HOTFIX_20261024.md`.


### NATIVE-05 hosted AndroidTest package identity (2026-10-24; run 40103583694)

- **Evidence:** <https://github.com/Mikeyphw/skybind/actions/runs/40103583694>, SHA `19cfccf812a2afc3afcc169d4cb3d6b6263d03f9`. App and AndroidTest APK compile and signing tasks PASS, verifier exits `COMPILED_MANIFEST_PACKAGE_IDENTITY_INVALID:app-personal-androidTest.apk`; candidate upload skipped. Failure diagnostics printed only filenames while invoking bare `aapt` through a grep filter; unlike the verifier, this diagnostic did not resolve the SDK tool explicitly.
- **Root cause candidate:** strict compiled-manifest reader demands `android:versionCode` on generated instrumentation package. Test APK version fields may legitimately be absent; accepting absence *only for AndroidTest* preserves genuine signer, bytes, package, SDK, instrumentation-target validation. Confirm actual compiled fields from repaired bounded diagnostics on next hosted run.
- **Repair:** explicit nullable test version code, strict production version, reject malformed/contradictory present metadata, and use same SDK-resolved `aapt` for diagnostic field presence.
- **Devtool improvement status:** SOURCE IMPLEMENTED; HOSTED RE-QUALIFICATION PENDING; do not treat source or compilation as evidence of artifact publication or device authorization.


### 2026-10-24 — Devtool / Skybind hosted AndroidTest blank-badging denial (NATIVE-05)

- **Evidence:** GitHub [40109002928](https://github.com/Mikeyphw/skybind/actions/runs/40109002928), commit `c680f317e7c75395f4b1699b7568e98cd9bb16d0`. Both Android APKs compile; metadata verifier rejected `COMPILED_PACKAGE_IDENTITY_UNAVAILABLE:app-personal-androidTest.apk`; upload skipped. Diagnostic found compiled test XML `package`, min/target SDK and instrumentation target but no version fields. Exact badging values not retained.
- **Affected:** Skybind `scripts/dev/android/personal_apk.py`, hosted diagnosis, `tests/test_native05_personal_apk.py`, `scripts/dev/android/native05_personal_apk_gate.py`; Devtool source validation, not Devtool overlay engine.
- **Root cause / fix:** Before binary manifest fallback, the test badging parser rejected present-but-empty `versionCode=''`; now normalize only that role's empty code as null, require compiled XML for every AndroidTest APK and compare all present identity claims, preserving signer, strict app version and tests' instrumentation target. Disallow contradictory, malformed and duplicate badging fields. Diagnostic now reports value *presence* only.
- **Improvement recommendation:** General Devtool external-release acceptance should distinguish source parser regressions from hosted byte evidence; keep raw CI diagnostics bounded, exact artifacts and post-run provider qualification authoritative; avoid serial guess-driven changes.
- **Status:** SOURCE_IMPLEMENTED; FULL_SOURCE_REGRESSION_PASS; HOSTED_ARTIFACT_VERIFY_OPEN; DEVICE_INSTRUMENTATION_OPEN; OWNER_APPROVAL_OPEN. See `docs/qualification/NATIVE_05_ANDROIDTEST_BADGING_EMPTY_CODE_FIX_20261024.md`.

### 2026-10-24 — NATIVE-05 personal APK permission-report divergence (CI 40117550163)
- **Concrete evidence:** `Skybind Personal APK (candidate only)` run [40117550163](https://github.com/Mikeyphw/skybind/actions/runs/40117550163), SHA `3f09ec5c08021c4503b47dd4b5faa06a3dde3a17`, passed both APK compiles and signing setup; `personal_apk.py create` returned `COMPILED_PERMISSION_DRIFT`, upload skipped. CI diagnostic reported app/test package identities but no permissions. It is **unknown** whether the hosted `aapt dump permissions` underreported the four reviewed permissions or the merged APK contains an extra permission. Do not invent a permission inventory.
- **Affected projects:** Skybind personal APK GitHub Actions, `scripts/dev/android/personal_apk.py`, native-05 source guard, diagnostic worker, source tests. No change to existing module/daemon or to real-device/root-manager permissions.
- **Source remediation:** On incomplete `aapt dump permissions`, verify actual compiled `AndroidManifest.xml` from the **APK bytes** and enforce the unchanged four-item permission allowlist there, with complete identity cross-check. Any unexpected secondary-report permission, extra/missing compiled permission, or identity drift still blocks release. Diagnostics now emit bounded public permission names and missing/extra sets from report and manifest, not secrets or raw XML. Added adverse and positive regression tests.
- **Status:** SOURCE REPAIRED / HOSTED VERIFICATION OPEN. No release candidate or device qualification from the failed CI run. If the next hosted run reports extra merged privileges, this is a genuine blocker and must be corrected at manifest-merger/source level. **Devtool improvement:** add first-class compiled APK permission-inventory provenance and fail-only sanitized manifest diagnostics before repeated candidate builds; link permission source-merger evidence to CI receipts. OPEN cross-project capability enhancement.


### NATIVE-05 / CI 40119051809 — dependency-merged signature permission inventory (2026-10-24)

- **Concrete evidence:** GitHub Actions personal candidate run `40119051809` (SHA `bfafb6268a978f46a1b3226fea7aae2709aa16be`) compiled both APKs but `personal_apk.py create` failed `COMPILED_PERMISSION_DRIFT:app-personal.apk`; no candidate artifact uploaded. Diagnostic compiled/aapt reports agreed on five app permissions, including `io.github.mikeyphw.skybind.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION`, and AndroidTest separately showed `android.permission.REORDER_TASKS`.
- **Affected projects/modules:** Skybind NATIVE-05 GitHub hosted APK release verifier and generated manifest; `scripts/dev/android/personal_apk.py`, `personal_apk_diagnostics.py`, source gate, tests; dependency-linked AndroidX Core. Device qualification and owner approval still pending. No evidence of Devtool engine failure.
- **Source repair:** Include exactly the app-scoped injected AndroidX receiver permission in the five-permission allowlist, **only when compiled XML proves its unique `<permission>` declaration is signature-only**. Parse compiled XML even if aapt's permission report already matches; reject weaker levels, mismatched/duplicate definitions, extra or missing uses-permissions, drift in package/version/SDK, and unknown names. Record verified protection in byte-bound manifest, retain signer and test-target verification. Add direct negative regression cases, update historical acceptance documentation.
- **Devtool improvement:** Differentiate explicit source permissions, generated/dependency-merged permissions, and standalone instrumentation package permissions. Preserve a bounded direct compiled-permission diagnostic in CI rather than assumptions or a permissive wildcard. Attach exact run evidence and code path to cumulative ledger. **Status: SOURCE_FIX_PREPARED; hosted signed pair, device, full instrumentation, release owner approval UNQUALIFIED pending new run.**

### 2026-10-24 — NATIVE-05 compiled AndroidX signature protection typed integer (CI 40120472501)

- **Evidence:** GitHub Actions https://github.com/Mikeyphw/skybind/actions/runs/40120472501, source `bd24aa13640e1bd0e9c13653e87cef590eff28c9`. Both personal APKs compiled and signing setup succeeded, but candidate verification rejected `COMPILED_MANIFEST_ATTRIBUTE_TYPE_INVALID:android:protectionLevel:app-personal.apk`, skipping publication. Diagnostics listed exactly the five reviewed app permissions but couldn't parse the compiled XML permission declaration.
- **Affected:** `scripts/dev/android/personal_apk.py` compiled XML `aapt` parser; source integrity gate and regressions. No changes required to Android Java/Kotlin app or Devtool engine.
- **Remedy:** Accept Android `aapt` typed flag/enum integer `0x11` *only* on `android:protectionLevel`, keep 0x10 on other integer identity attributes, compare entire numeric protection mask to `2` signature-only, reject all flag additions and unknown typed values, require matching app-owned private permission declaration. New source negative fixtures verify weaker/overbroad/unknown masks, bad encodings and scope isolation.
- **Devtool improvement:** Maintain source-backed fixtures for common Android build-tool wire representations (decimal integer vs enum/flags), rather than a verifier format assumption that repeatedly fails only in hosted CI. Preserve bounded diagnostics, exact source/bytes provenance and truthful negative release gates. **Status:** SOURCE FIX TESTED (172 Python regressions, native gates, complete Go suite) / HOSTED APK SIGNATURE VERIFICATION OPEN / DEVICE INSTRUMENTATION OPEN.


## 2026-10-24 — Skybind NATIVE-06 Android Compose test-host omission

- **Evidence:** real NATIVE-06 receipt `native06-ed1a289c135b43c8b4b5234568eb29a3.json`, first readonly lane `realNavigationHasFiveDistinctPages`, private navigation log `Unable to resolve activity for: ... cmp=io.github.mikeyphw.skybind.test/androidx.activity.ComponentActivity` (run 40124935243, f6d48d49). Zero lanes completed; instrumented navigation not executed. Source checkout has debug-only `ui-test-manifest` but hosted APK uses non-debuggable `personal` testBuildType.
- **Affected:** Skybind personal androidTest manifest packaging, Compose UI instrumented tests, NATIVE-06 source gate and device acceptance, GitHub signed APK candidate / exact-source provenance; Devtool release diagnostic workflow. No current evidence of production UI defects.
- **Recommended remediation:** Add test host `androidx.activity.ComponentActivity` ONLY to `androidTest/AndroidManifest.xml`; explicitly deny export/launcher/permission drift into production via tests, preserve non-debuggable app and fail-closed NATIVE-06 receipts. The new test APK must prove the resolved host on the device; source tests alone are insufficient.
- **Devtool enhancement:** Host CI should perform post-build APK manifest component checks for all required instrumentation activities and verify they launch on a real device before declaring device qualifications. Use compiled manifest and live test logs as first-class evidence. **Status:** SOURCE_REPAIR_IMPLEMENTED; HOSTED_REBUILD_REQUIRED; DEVICE_READONLY_RETRY_PENDING; FULL_MODULE_EVIDENCE_PENDING; OWNER_APPROVAL_OPEN.


## 2026-10-25 — NATIVE-06 cross-process Compose fixture host (real Android v3)

- **Evidence:** Real-device NATIVE-06 version 3, hosted run [40135828322](https://github.com/Mikeyphw/skybind/actions/runs/40135828322), source `4ccbed5138d0af413fcb42318429cf5024a9c9c4`, signed paired app/test installed successfully; first `NativeUiTest#realNavigationHasFiveDistinctPages` failed with `Intent in process io.github.mikeyphw.skybind resolved to different process io.github.mikeyphw.skybind.test ... ComponentActivity`. No navigation assertion executed. Prior separate test-package host was packaged and launchable, but in the wrong process.
- **Affected:** Skybind AndroidTest Compose fixtures (`NativeUiTest.kt`, `NativePolishUiTest.kt`, `RemoteBrowserTest.kt`), androidTest manifest, `native06_source_gate.py`, qualification documentation and source regressions. Production Skybind manifest, daemon, root authority and signing implementation unchanged. This is a test harness packaging/process bug, not yet evidence of UI malfunction.
- **Fix / recommendation:** Bind fixture rules to target app `MainActivity` with `createAndroidComposeRule<MainActivity>()` and explicit UI-thread replacement of Compose content; remove test APK `ComponentActivity` manifest host. Source-gate wrong-process, unexpected exported hosts, unsafe Gradle host merge and old rules. **Devtool improvement:** add Android instrumentation target-process/host identity checks to signed paired-APK hosted/installed qualification, and run actual device smoke instrumentation before accepting test-harness configuration. Build-only source gates cannot establish ActivityScenario process identity.
- **Truthful status:** SOURCE_FIX_PREPARED; Kotlin hosted compile, Android 16 instrumentation, full same-source module, owner approval and final qualification ALL OPEN. Existing version 3 device receipt remains BLOCKED and cannot be reused. See `docs/qualification/NATIVE_06_COMPOSE_CROSS_PROCESS_HOST_HOTFIX_20261025.md`.

### NATIVE-06 Android 16 Compose config consent semantics/accessibility (2026-10-25)

- **Evidence:** source commit `c767e42c4fb605f61bb9e0fc402e5b1c673b625b`, hosted candidate run `40158114373` success, rooted device private receipt `native06-b682c5badeed49b38552fa949c80d520.json` with three passing lanes and blocking `configApplyRequiresReviewConsent`; `navigation`/`mount-ui`/`mount-consent` passed. Device stack reports `Failed to inject touch input` / zero semantics nodes with `TestTag = config-consent`.
- **Issue:** Consent checkbox was nested inside the review-details `heightIn(max = 480.dp).verticalScroll` block while Apply stayed in the separate footer. Unmerged/viewport-sensitive accessibility of the inner Material checkbox is unverified; do **not** infer disabled consent policy or a successful bypass from the log.
- **Repair:** dedicated fixed-area `Role.Checkbox` consent row with one clickable semantics node; gate Apply on checked and not busy, reset across proof ID; explicit off/on device assertions plus source negative tests. Preserve production permission/signature/root scope.
- **Status:** source-remediated in proposed exact-source hotfix; new GitHub Android build and real-device NATIVE-06 read-only must validate (not yet qualified).
- **Recommendations:** record per-lane UI semantics-tree evidence in private logs on node-not-found; batch independent read-only lane probes before successive hosted rebuilds when authorized. Keep 0-SKIP and explicit owner review gates unchanged.


## NATIVE-06 Android 16 signer disclosure accessibility (2026-10-25)

- **Evidence:** signed personal APK v5, source `3f022fcbf865fbd75eb1d94438ce013352032278`, NATIVE-06 receipt `native06-b0441d23b3ad42e7b606aa5844596a2e.json`: four readonly lanes pass; fifth `polish` fails at `NativePolishUiTest.kt:63` after clicking the signer control; `about-signer-sha256` is absent from the Compose test semantics tree.
- **Affected surface:** `android-app/.../ui/SkybindApp.kt`, `NativePolishUiTest.kt`, `scripts/dev/android/native06_source_gate.py`, NATIVE-06 personal Android instrumented acceptance.
- **Recommended/delivered source change:** show read-only installed APK fingerprint in a modal Material `AlertDialog` rather than a conditional card after the scrollable More page. Give fingerprint, dialog and Close individual semantics tags; assert open/content/dismiss states in instrumentation; negative source regressions check contract. No changes to signing/permission/root authority.
- **Status:** SOURCE FIX PREPARED; hosted compile and real-device rerun OPEN. Do not count v5's four passed lanes as new-source qualification; preserve evidence without overstating closure.
- **Tooling improvement:** establish a recurrent Android UI semantics smoke gate for expanded More-page content to detect elements present in source but missing from the real device semantics tree. **OPEN**: independent device evidence and broader coverage.


### 2026-10-26 — NATIVE-06 signer dialog semantics ambiguity (personal APK v6)

- **Evidence:** hosted source validation run `40329439396`, signed APK candidate run `40329441768` (SHA `89eab0cca02f618c6a3c186e7bff8b3089c7bdbf`, versionCode 6). Physical Android 16 `native06-ca5a6c4f7d94486d8af8a2575011a0f6.json` passes four read-only lanes (`navigation`, `mount-ui`, `mount-consent`, `config-consent`) and fails `polish` at merged `about-signer-dialog` assertion following a successful click. The evidence does not establish whether the dialog is uncomposed or only unfindable in the merged semantics tree.
- **Affected:** Skybind `NativePolishUiTest.kt`, source gate, source mutations, read-only personal APK qualification. Devtool cross-project improvement surface: bounded Android semantics diagnostics and fail-closed receipt classification. No evidence of Devtool engine fault.
- **Source change A:** test-only merged/unmerged signer-tag cardinality probe with no raw text logged; assert unmerged dialog + exact displayed certificate SHA-256 + visible Close + post-close absence, wrapping failed assertion with tag-count evidence. Fail-closed source guard, negative mutation suite, same-source hosted pair still mandatory. Production Compose dialog unchanged.
- **Deferred change B:** only hoist dialog state or adjust Material3 wrapper if device evidence proves a real composition/state issue. Explicitly do not reuse four v6 historical PASS lanes as v7 PASS.
- **Recommendation:** a shared Devtool Android test helper that records per-tag tree cardinality in private instrumentation outputs, with a strict allowlist and fail-closed parsing (avoid raw semantics dump, uncontrolled PII/secret disclosure, and release-gate bypass). **Status:** CHANGE_A_SOURCE_PREPARED; GITHUB_ANDROID_COMPILE_OPEN; DEVICE_SEMANTICS_PROBE_OPEN; RELEASE_AND_OWNER_APPROVAL_OPEN. See `docs/qualification/NATIVE_06_SIGNER_SEMANTICS_DIAGNOSTIC_20261026.md`.

### 2026-10-26 — NATIVE-06 hosted AndroidTest compile failure (v7 attempt 1)

- **Evidence:** GitHub Actions run [40394246393](https://github.com/Mikeyphw/skybind/actions/runs/40394246393), source `3e8a9101476fcb5fc412b702dbf06eb934730873`. JDK/SDK, source/signer admission and production Kotlin compilation passed. `:app:compilePersonalAndroidTestKotlin` failed at `NativePolishUiTest.kt:88:34`: unresolved reference `NativePresentation`. Verification/publishing were skipped; no APK pair was uploaded. Source Python checks had passed but never compiled the AndroidTest source.
- **Root cause:** `NativePresentation` is declared under package `io.github.mikeyphw.skybind.ui`; the new diagnostic file referenced `NativePresentation.signer(compose.activity)` from package `io.github.mikeyphw.skybind` without importing it. This is a test-only compile bug, not a device, daemon or signing failure.
- **Hotfix B:** add the exact Kotlin UI package import; source gate now requires that import and the named declaration/function; two negative mutation regressions reject missing/wrong package imports. No production behavior, signer, manifest, package identity or device data changed.
- **Devtool improvement:** Add a generic pre-host-dispatch compile/import validation phase for changed Android `androidTest` sources when a compatible build host exists; in source-only Termux mode explicitly report `NOT_COMPILED` and treat hosted compilation as a hard downstream gate. Python token/source tests alone cannot guarantee Kotlin resolution.
- **Status:** SOURCE_HOTFIX_PREPARED, **HOSTED_COMPILATION_OPEN**, paired APK verification OPEN, installed device semantics and release authority OPEN. Do not re-run failed exact-source build: a new commit must generate a new source-bound v7 APK pair.

### API-01 native rclone layout, 2026-10-26 (source candidate, qualification open)
- Evidence: module system/bin/rclone originally contained upstream ELF; release and Go runtime authority pinned ELF at same path, preventing transparent Skybind-default launcher without coordinated change. Source paths: `scripts/dev/release/skybind_release.py`, `internal/paths/paths.go`, `internal/integrity/integrity.go`, `module/customize.sh`.
- Improvement: source-bound composition moves unmodified ELF to `system/bin/skybind-rclone-engine`, delivers a deterministic `system/bin/rclone` wrapper, and accounts for both in installed runtime provenance. Native jobs/mounts use ELF directly; externally invoked `rclone` defaults to private Skybind config. R1 grants retained for legacy consumers.
- Limitation: PATH visibility depends on active Magisk/KernelSU module mount; non-root app UIDs cannot access root-private config; concurrent native rclone config changes need separate API-02 conflict qualification. Do not claim device acceptance.
- Status: IMPLEMENTED_IN_SOURCE_UNQUALIFIED, device/API-02/API-03 OPEN. Require provider-bound build, module package verification, real-device mount/CLI/consumer tests before owner approval.

### 2026-10-26 — API-01 promise audit and candidate CI regression (R2)
- **Evidence:** source audit of `SKYBIND_API01_NATIVE_RCLONE_20261026.zip` found missing advertised `/system/bin/skybind-rclone` alias. Original candidate workflow executes `test_q05p7_local_wrapper.py`, where tests erroneously reject the already-reviewed Go 1.27.3 local-only compiler despite production compatibility accepting it; three stale expectations fail.
- **Affected:** module candidate layout, installed runtime provenance and Q12/Q13/Q15 inventory, KernelSU installer, deterministic packaging, Q05P7 tests, CI source checks, Devtool validation.
- **Repair:** add byte-identical public alias, verify it by module candidate and Go runtime hash inventory, include in install checks and reproducibility receipts. Align test expectations with **existing** Go 1.27.2 CI pin + explicit local-only Go 1.27.1/1.27.3 allowance. No pin, signing secret, owner approval, daemon privilege or remote mutation changed.
- **Status:** SOURCE_REPAIR_READY, hosted candidate build and real Android `/system/bin` PATH + config override + BKX/chrootctl acceptance OPEN. Never reclassify earlier real v6 Android evidence.


### 2026-10-26 — API-02 root-local managed-feature gateway, mutation replay admission

- **Evidence:** `internal/featureapi/feature.go`, `cmd/skybind/feature.go`, `internal/daemon/feature_capabilities.go`, focused Go tests, Devtool `api02-managed-features` DAG and `scripts/dev/android/api02_source_gate.py` with mutation-negative tests. Source-only; no installed package or device qualification.
- **Finding:** The 57-operation internal API and namespace/mount controllers already implement preview/proof and root ownership, but no stable external feature facade exists; normal journal `StartRequest` stores IDs **without deduplicating** same request IDs. An external consumer may inadvertently replay an ambiguous mutation.
- **Implemented:** strict v1 root-only CLI through the same-UID private daemon; finite feature capability negotiation truthful to actual handlers; JSON-only stdin, no rclone or config API; feature-only serialized duplicate-mutation refusal backed by existing journal; read `operation.status` for lost-reply reconciliation. Internal normal CLI, R1 broker, root-manager module and native rclone paths remain unchanged.
- **Limits:** feature-only locking does not magically dedupe concurrent writes sent through unrelated legacy transports. `operation.events` is optional and advertised implemented only when spool registered. Real FUSE/namespace/Android/SELinux and signed module builds still OPEN. BKX non-root transport is **not** made available by running a `su` child; verify independent identity and permissions in API-03.
- **Devtool backlog:** consider a common shared idempotency key/reservation primitive at `journal.StartRequest` for all authenticated transports, preserving current on-disk receipts and compatibility; require explicit recovery semantics and negative tests before changing core globally. Consumer capability manifest must track only truly implemented source and independently attested device behavior.
- **Status:** IMPLEMENTED_SOURCE_ONLY, DEVICE_AND_CROSS_UID_UNQUALIFIED, release/owner approval OPEN. No automatic device install or grants.
