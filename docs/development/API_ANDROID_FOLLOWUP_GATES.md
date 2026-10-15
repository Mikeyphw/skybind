# A1–B3 two remaining Android device gates — source-bound follow-up v1

**Not a release qualification.** The earlier **14 PASS / 0 FAIL / 2 BLOCKED** backend runner must *not* be repeated merely to change its two hard-coded BLOCKED results. Raw green-run archive has not been supplied. These separate jobs collect additional observations and remain fail-closed. They do not alter the original runner or CFS1 obligations.

Source pin for this set: `1e2257595598c3b983554a84483680152baa076d` (wrapper install-retention commit). Changes are intentionally only to Devtool wrappers, WebUI diagnostics, and device test scripts. Do not apply if source diverges; regenerate a reviewed overlay instead.

## 1. Actual KernelSU WebView baseline

1. Apply the source-bound overlay, validate, then build/install a **personal** module explicitly via the existing `./devtoolw personal-release -i` process. The new WebUI JS must be installed; a source-only patch is not enough. Reboot intentionally if required by your installed module manager.
2. In the real KernelSU (or KernelSU Next) embedded Skybind WebUI, open **More → Device qualification (read-only probe)**. Tap **Observe embedded transport**, then **Copy sanitized receipt**. Inspect the JSON (it contains no remote paths, job names, tokens, stdout/stderr or secrets). Save that JSON as a file accessible to Termux, for example `~/Downloads/skybind-webview-probe.json`. This capture is intentionally in-WebView, not the CLI bridge.
3. From Termux, set `SKYBIND_QA_WEBVIEW_RECEIPT` to that exact file and run `./devtoolw api-webview-gate`. While the foreground collector's **12-second countdown** is active, switch from Termux back to KernelSU with the Skybind WebView visible. If the manager is KernelSU Next, set `SKYBIND_QA_MANAGER_PACKAGE=com.rifsxd.ksunext` first. The collector samples only the *resumed* manager activity (not historical dumpsys entries), verifies the installed WebUI JS hash, and checks the recorded embedded callback envelope. No screenshot or UI text is exported.
4. Upload the resulting `/storage/emulated/0/Download/Skybind-API-Device-Tests/skybind-webview-raw-*.zip` for independent review. A source read-only probe and resumed manager **do not** prove visual navigation, UI previews/confirmation, in-flight progress, leave/reopen, cancel, or transient-error safe retry. These stay **BLOCKED** until separate legitimate device evidence exists.

The in-page observer uses only `operation.events` and `jobs.status` through the actual selected embedded `ksu.exec` bridge. It never writes remote objects, cancels a job, modifies offline state, or injects transport errors. It uses sessionStorage only for a sanitized cursor to aid a repeat read-only observation; it does not claim WebView close/reopen occurred. The receipt is untrusted client-side evidence and cannot itself serve as a release seal.

## 2. Pre-/post-reboot event and offline metadata

1. While the installed module is working, run `./devtoolw api-boot-prepare` in Termux. This writes `skybind-boot-pre-<session>.json` to Android Downloads. The collector snapshots kernel boot identity **as a SHA-256**, installed Skybind binary SHA, event cursor, job counts, CE state, and **only SHA-256 digests** of fixed private event/job/offline journal files. It never reads out or exports private content.
2. Record the exact preboot JSON path. **The job never performs a reboot.** If you authorize it, reboot Android yourself. After unlocking and CE readiness, set `SKYBIND_QA_BOOT_PREPARE` to the saved preboot path and run `./devtoolw api-boot-verify`.
3. The verifier checks distinct kernel boot IDs, unchanged installed ELF, nonregressing durable event cursor, unchanged queued-edit/review ledger digests, and `sys.boot_completed` / CE readiness. If a source change or queue edit happened meanwhile, interpret carefully: the collector fails closed and does **not** automatically reconcile differences.
4. If you intentionally launch a **test-owned disposable job** that is still RUNNING at prepare time, you may supply `SKYBIND_QA_OWNED_JOB_ID` **on both stages**. Verification checks `INTERRUPTED` state plus an actual `job.interrupted` event. **A user-supplied ID alone does not prove ownership**; independent test creation provenance remains BLOCKED. Never select or cancel preexisting user jobs.
5. Upload the resulting `skybind-boot-verify-<session>.zip`. This pass cannot prove delayed unlock across multiple boots, ordinary app-UID mount access, all FUSE namespaces, root-manager early boot autostart, or writeback replays. Those remain outstanding.

Never point any B3 testing at real user data or the live writeback path. Preserve queued offline edit `QUEUED` with revision `UNKNOWN`. No test here flushes, discards, copies, reconciles, edits, or auto-retries user offline content.

## Command summary

```sh
cd "$HOME/Code/skybind"
# Existing application source must be an exact match for the overlay.
# After intentional install, use the real KernelSU WebUI to copy the JSON.
export SKYBIND_QA_WEBVIEW_RECEIPT="$HOME/Downloads/skybind-webview-probe.json"
# For KernelSU Next only: export SKYBIND_QA_MANAGER_PACKAGE=com.rifsxd.ksunext
./devtoolw api-webview-gate

./devtoolw api-boot-prepare
# Reboot manually ONLY with the user's authorization, then unlock.
export SKYBIND_QA_BOOT_PREPARE='/storage/emulated/0/Download/Skybind-API-Device-Tests/skybind-boot-pre-SESSION.json'
./devtoolw api-boot-verify
```

For every report, retain the exact raw evidence; a Devtool job exit 0 is **not** proof that the cases qualify. Separate installed binary hash ↔ build recipe/receipt ↔ source and provider reproducibility remain P0. Pending visual, startup, offline, event stress, B3 race, full B4–E roadmap and formal G01–G08 remain unchanged.
