# V9 — Interactive WebUI X acceptance: development and Android runbook

Status: **IMPLEMENTED IN SOURCE / HOST-SIDE TESTED / NOT ANDROID EXECUTED / NOT RELEASE QUALIFIED**.

This adds four *independent* acceptance paths around the actual Skybind WebUI in the
user's spoofed WebUI X v438-release (`vtebo2.rezdpneqo9vt.d2wjkhzv77ptrycwv`).
It does NOT change the accepted A1–B3 backend 14 PASS or passive reboot 5 PASS.
No automatic Android reboot, cancellation, removal, offline journal modification,
or operation start occurs in the UI qualification collector.

## Inputs and setup

1. Apply the V9 source-guarded patch to the exact V8 source checkout. A candidate
   module rebuild/reinstall **is needed**, because `module/webroot/bridge.js`,
   `index.html`, and a new `interactive_qa.js` change installed WebUI assets. The
   source patch does not automatically install a module.
2. Run `./devtoolw personal-release -i` through the existing intentional review
   workflow and verify `module/webroot/interactive_qa.js` is installed. Build
   identity remains unqualified until provider-to-installed proof is established.
3. In WebUI X → Skybind → More → V9: Interactive device qualification, use the
   isolated controls. No QA button invokes run, cancel, remote delete, or reboot.
4. For safe read-only A (navigation), navigate to Remote browser and choose
   two non-root folders by the actual browser. Choose **Check (read-only)**,
   click **Preview transfer policy**; navigate back to More and select
   **Inspect actual navigation**. Android accessibility readback and actual
   host-foreground correlation must also succeed in the device collector.
5. For D (read-only bridge recovery), select **Exercise read-only recovery**.
   It drives existing Jobs polling and injects *one synthetic failure* into
   `operation.events` **before native dispatch**, then verifies bounded retry,
   monotonic cursor and no run/cancel dispatch. It is **not** a real kernel or
   manager outage and must not be reported as such.

## Opt-in fixture for progress and cancellation

Use only an intentionally chosen remote **non-root** test folder with no offline
queued edits. No fixture operation is allowed without both explicit variables:

```sh
export SKYBIND_QA_REMOTE_BASE='YOUR_REMOTE:YourExistingDisposableParent'
export SKYBIND_QA_ACK='I_AUTHORIZE_DISPOSABLE_V9'
cd ~/Code/skybind
./devtoolw api-webui-interactive-prep
```

The preparer creates an unpredictable `skybind_v9_<hex>/source` and `destination`
subtree in that base, seeds an 8 MiB file, and waits for that fixture upload to
finish. **These are setup operations, not repeated A1–B3 acceptance tests.**
Their results are not counted toward WebView PASS cases. It writes a private
0600 ownership record at `~/.local/state/skybind-qa-v9/<session>.json` and
reports its path; no remote endpoints are sent in the public ZIP. Use these
commands locally to view the source/destination paths for UI selection:

```sh
jq -r '.source,.destination' ~/.local/state/skybind-qa-v9/skybind_v9_<SESSION>.json
```

In actual WebUI X, select those exact paths through the **Remote browser**.
Choose **Copy (skip existing)**. Preview, then confirm with the normal Skybind
button. Capture the newly generated run ID from Skybind's notice or authoritative
Jobs/Activity. Enter it in the V9 field. If still active, capture progress,
close/reopen WebUI X, and select verify. For cancellation, use the **ordinary
Skybind Cancel run button** for **that exact test-owned run**; then select V9
verification. Do not cancel other operations; cancellation may race completion
and remain BLOCKED.

The fixture uploader does **not** clean up automatically or overwrite anything
outside the unique folder. Review and remove disposable objects separately when
safe. The original M0–M8 manual cases stay deferred.

## Collect an evidence ZIP

After generating and copying a fresh (≤15 minutes) sanitized V9 receipt:

```sh
cd ~/Code/skybind
export SKYBIND_QA_WEBVIEW_HOST='vtebo2.rezdpneqo9vt.d2wjkhzv77ptrycwv'
export SKYBIND_QA_V9_RECEIPT='clipboard'
export SKYBIND_QA_V9_OWNERSHIP="$HOME/.local/state/skybind-qa-v9/<session>.json"
./devtoolw api-webui-interactive-gate
```

Switch back to Skybind in **WebUI X** for the two consecutive live foreground
samples and the in-memory Android accessibility dump. The collector emits
`skybind-webuix-v9-*.json` plus ZIP in `Download/Skybind-API-Device-Tests`.
It exports no raw XML, remote paths, passwords, queued edits, or logcat.

## Acceptance boundaries

- **A navigation:** requires trusted UI navigation, read-only preview, enabled
  confirmation, same installed QA JS, host foreground, and in-memory native
  Android accessibility evidence containing Skybind and preview control. If
  WebUI X exposes no WebView accessibility nodes, stays BLOCKED. No image
  screenshot is generated or claimed by V9.
- **B reconnect:** records distinct WebUI documents, bounded event replay,
  cursor monotonicity, and authoritative job state. **Full close/reopen remains
  BLOCKED** until a distinct native host Activity exit/return trace is captured.
- **C cancellation:** actual UI Cancel-run click, source+destination SHA-256
  matched to private fixture, new non-baseline run ID, and authoritative
  `jobs.status=CANCELLED` + `job.cancelled` event required. Completed-before-
  cancellation is BLOCKED, not a test failure or an accepted cancel.
- **D recovery:** scoped synthetic read-only callback fault PASS can be recorded
  if recovery and no duplicate mutating dispatch are observed; **true external
  ksu.exec interruption** remains a distinct BLOCKED obligation.

All client-reported observations remain `RAW_UNATTESTED_NOT_RELEASE_QUALIFIED`.
The source-to-installed ELF chain, test-owned interrupted-job reboot, offline
writeback conflict/CE cold boot, G01–G08 release gates, and complete A–E roadmap
remain open and unchanged by this V9 patch.
