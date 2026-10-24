# NATIVE-06 — Personal native APK release acceptance

**State: source implementation delivered; actual GitHub/Android/device gates NOT EXECUTED.** This does not modify previously approved Skybind personal module evidence or make an independent certification claim. The new APK is not approved until an exact hosted candidate, matching locally-built daemon/module, on-device test execution and explicit new owner acceptance have all succeeded.

## Proof obligations and evidence

| Promise | Implementation | Evidence executed here | Remaining live gate |
|---|---|---|---|
| Same-source GitHub personal APK + AndroidTest | NATIVE-05 hosted personal workflow; NATIVE-06 `preflight`, GitHub live lookup, exact commit/bytes/signature | Python positive/negative source tests PASS | Push to main, dispatch hosted workflow; upload immutable candidate receipt |
| Match installed APK/test signer/version/bytes | `personal_apk_device.inspect_installed` in NATIVE-06 preflight | Mock negatives PASS | Install only via NATIVE-05 explicit opt-in upgrade, verify installed pair |
| Same-source rooted Skybind daemon/module | NATIVE-06 `verify_matching_module`; verify PERSONAL_BUILD.json source, module ZIP hash and embedded `system/bin/skybind` against actual installed daemon sha256 | Fail-closed source tests | Build & explicitly install a matching module separately; capture device binary SHA |
| Auto-root without manually pressing Connect | `NativePersonalLiveTest.automaticForegroundRootNoManualConnect` + cold relaunch repeat | New Kotlin instrumentation source | Run on the installed personal candidate with persistent root manager grant |
| Mounts report daemon state | `NativePersonalLiveTest.mountsMatchAuthoritativeDaemon` | New Kotlin instrumentation source | Full real daemon, 0/running/stopped/degraded where present |
| Typed mount lifecycle and reconcile | `NativePersonalLiveTest.disposableMountStartRestartStopReconcile`, anonymous test-owned mount, proof-bound actions and cleanup | New Kotlin instrumentation source | Run only with four consent flags, isolated idle registry, selected test remote; fail if cleanup incomplete |
| Create/edit/rollback/delete & configuration safety | Existing `NativeMountConfigLiveTest` test-owned disabled mount | Existing AndroidTest source checked | Execute on selected physical/root-enabled device |
| Browser / Home / Jobs / Activity / BKX / security | Source-authenticated live acceptance matrix plus native UI negative & polish cases | Native source tests run | Hosted app/test APK on device; no skipped/assumption outcomes |
| Old nine-lane M2/M3 job behavior | Exact relevant live M3 preview, CHECK, cancel, COPY; target-side hash-verified prepared fixtures | Source contracts; existing previous receipts remain historical | New exact signed personal pair on device; explicit mutation opt-ins and prepared fixtures |
| Root reconnect after app kill | Android app-only force-stop/relaunch, PID identity and repeat no-Connect live test | Script source + negative tests | Execute under explicit app force-stop consent |
| Separate owner-scoped APK approval | `native06_personal_acceptance.py approve/check`, immutable evidence hashes and revocable/no raw root authority | Receipt mutation/replay/skip negatives PASS | Only after full device receipt, explicit new UI/root/mount/personal-scope approval |
| Other root managers, Android versions, devices | Explicitly excluded from approved scope | No evidence claimed | Separate qualification, no automatic extension |

## Required order of operations

1. Apply NATIVE-06. Commit/push **all** NATIVE-00…06 source to `main`; verify the hosted workflow exists there. Prior NATIVE-05 applied *locally* is not proof it was pushed.
2. Run **Skybind Personal APK (candidate only)** on GitHub Actions, `main`, with a monotonically increasing `version_code`, then inspect the actual workflow run. `gh workflow run skybind-personal-apk.yml --repo Mikeyphw/skybind --ref main -f version_code=2` is an example ONLY if 2 exceeds the installed APK. Never assume it does.
3. `python3 scripts/dev/android/personal_apk_device.py fetch --run-id <REAL_RUN>`; separately inspect dry-run `... device --folder ... --serial <SERIAL> --source-sha <EXACT_SHA>`; authorize `--install` only if preflight accepts signer/version continuity.
4. Build **matching** `./devtoolw personal-release` bclone module on current source. Check `PERSONAL_BUILD.json` (`source.commit` = same exact SHA as new APK) and `Skybind-bclone-PERSONAL.zip`; explicitly install/activate this module via root manager and reboot if required. The NATIVE-06 runner checks the installed daemon executable SHA against this ZIP; merely creating the ZIP is insufficient. Backup root module data before changing installed modules.
5. Test first in readonly profile (never installs, changes root grants or starts jobs). Run full profile only on an isolated test configuration, with explicitly prepared M3 CHECK/COPY fixtures and all four operation consent flags. Do not use full with an active mount registry: global Reconcile may impact unrelated mounts.
6. Inspect `~/.local/state/skybind/native-personal/native06-*.json`, including each exact PASS lane. The runner does not accept skipped tests or old receipt substitution.
7. Review launcher icon/mask, notification/splash, root prompt/denial UX, Mounts/Jobs/Activity/BKX states and a backed-up config before explicit `approve` and `check` for this exact APK. Approval is *local personal* evidence, not certification.

Example (all placeholders require actual observed values):

```sh
cd ~/Code/skybind
python3 scripts/dev/android/native06_personal_acceptance.py run \
  --folder "$HOME/Downloads/Skybind-Personal-APK-<RUN>" \
  --serial '<DEVICE_SERIAL>' --manager kernelsu --profile readonly --remote '<REMOTE>'

python3 scripts/dev/android/native06_personal_acceptance.py run \
  --folder "$HOME/Downloads/Skybind-Personal-APK-<RUN>" \
  --serial '<DEVICE_SERIAL>' --manager kernelsu --profile full --remote '<REMOTE>' \
  --module-manifest '/storage/emulated/0/Download/<MODULE_FOLDER>/PERSONAL_BUILD.json' \
  --module-zip '/storage/emulated/0/Download/<MODULE_FOLDER>/Skybind-bclone-PERSONAL.zip' \
  --allow-disposable-config --allow-disposable-jobs \
  --allow-app-force-stop --allow-global-reconcile

python3 scripts/dev/android/native06_personal_acceptance.py approve \
  --folder "$HOME/Downloads/Skybind-Personal-APK-<RUN>" \
  --device-receipt "$HOME/.local/state/skybind/native-personal/<PASS_RECEIPT>.json" \
  --ui-reviewed --root-approved --mount-reviewed \
  --accept-personal-scope --accept-untested-managers

python3 scripts/dev/android/native06_personal_acceptance.py check \
  --folder "$HOME/Downloads/Skybind-Personal-APK-<RUN>" \
  --approval "$HOME/.local/state/skybind/native-personal/<APPROVAL_RECEIPT>.json"
```

## Truthful constraints

- No personal APK workflow was found on the GitHub default branch during implementation. The locally applied NATIVE-05 overlay is NOT evidence that the workflow has been pushed; no hosted run/installer/device receipt has been generated in this implementation session.
- Source tests and Kotlin AndroidTest *source* do not qualify compilation, root grant, actual mount operation, real UI screenshots or install/upgrade success.
- The owner approves only the tested root manager/device and exact APK bytes. Denied-root UX should be reviewed separately on the actual root manager; the runner cannot revoke root or impersonate a root-manager denial safely. Automated no-Connect and negative binder/UI-fixture tests are distinct from a real root-manager denial observation.
- `PERSONAL_NATIVE_APK_APPROVED` requires exact hosted, installed, module and full Android receipt plus explicit owner approval. The app and module are separate artifacts with separate qualification histories.
