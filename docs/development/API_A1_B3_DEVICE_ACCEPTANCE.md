# Skybind A1–B3 — physical-device acceptance campaign

This is a **raw device evidence collection protocol**, not an independent release attestation. It does not certify KernelSU WebUI interaction from CLI output, does not declare queued offline edits safe to flush, and never modifies mount or supervisor state. Source/reference: uploaded Skybind snapshot `skybind-20261014-132957-710135.tar.gz`, source-bound overlays A1 v1.1, A2, A3, B1, B2, B3, and Devtool snapshot `devtool-20261014-101930-737268.tar.gz`.

## Prerequisite: installed binary really includes A1–B3

Applying Devtool overlays to `$HOME/Code/skybind` changes *source*, **not** the installed KernelSU module. Build from this post-B3 source using the pre-existing wrapper, e.g. `./devtoolw test`, then (for the existing bclone personal track) `./devtoolw personal-release`. Inspect the generated local candidate, install it intentionally with KernelSU, and reboot once. Do **not** treat a successful build as installation or device acceptance. The module's installed-binary SHA-256 is recorded for later provenance reconciliation; a raw digest alone cannot prove it was built from the exact source.

## Launch using Devtool's own wrapper

From `$HOME/Code/skybind` in Termux:

```sh
./devtoolw api-device-readonly
```

To include read-only browsing on an existing remote folder without mounting it:

```sh
export SKYBIND_QA_REMOTE_BASE='configuredRemote:Skybind-QA'
./devtoolw api-device-readonly
```

The named folder must already exist. Use a disposable folder dedicated to testing. Never use a mounted writeback cache location or live user data.

## Disposable API qualification (opt-in)

Once read-only results succeed, **create an existing empty parent test folder** on a remote (for example through ordinary rclone setup or Skybind UI), then supply *that exact existing folder*:

```sh
export SKYBIND_QA_REMOTE_BASE='configuredRemote:Skybind-QA'
export SKYBIND_QA_ACK='I_AUTHORIZE_DISPOSABLE_TEST_DATA'
./devtoolw api-device-disposable
```

The runner generates a unique `qa_...` subfolder under that parent and only writes within it and `/storage/emulated/0/Download/Skybind-Transfers/qa_...`. **Do not use your mounted location, queued offline edit directory, or a non-disposable remote folder.** No cleanup/deletion is attempted; inspect evidence first, then remove test-only data manually if desired. If a job is still running at timeout it is reported BLOCKED instead of blindly resubmitted.

### Covered scenarios

| Check | Automated | Qualification interpretation |
|---|---|---|
| Installed CLI and direct WebUI bridge capabilities | Yes | Not equivalent to KernelSU `ksu.exec` in WebView |
| A1 cursor replay, gap/sequence, stored event queries | Yes | Current event spool only; restart persistence needs another run/boot |
| A2/A3 job snapshot and numeric metric schema | Yes | Per-transfer progress observations recorded where available; tiny jobs may have no intermediate sample |
| B1 remote listing and unsafe request denial | Yes | Requires specified existing remote folder |
| B1 safe copy, check, event lifecycle | Disposable mode | Only tests unique test data; status and event required |
| B3 remote mkdir, upload, download (SHA-256) | Disposable mode | Writes to unique test-only paths |
| B3 same-remote file move, destination conflict | Disposable mode | Source absence and destination presence verified |
| No-overwrite | Disposable mode | Attempts changed source upload and downloads destination; verifies unchanged SHA-256 |
| Cancellation | Disposable mode | Cancellation requested only on runner-owned job; races report BLOCKED |
| Actual KernelSU embedded WebUI end-to-end | **Not yet** | Needs device WebView interaction/screen and root-manager bridge evidence |
| Reboot/startup reliability and offline journal replay | **Not yet** | Must use separate existing startup/queued-edit tests and compare boot IDs |

### Evidence and interpretation

Records land at `/storage/emulated/0/Download/Skybind-API-Device-Tests/skybind-api-qualification-qa_*.zip`, each containing one JSON and Markdown report. A source fingerprint and installed binary SHA-256 are recorded. Raw remote paths, authentication data, RPC bodies, proof tokens, provider stderr, and job names are not exported. `PASS` is an observed check; `BLOCKED` is unproven; `FAIL` is a tested failure. Devtool may report the collector job as successful when tests were BLOCKED: **never convert that to an API qualification pass**. The JSON counts and per-check evidence are authoritative.

### Embedded WebUI device testing that remains necessary

In KernelSU's actual WebUI, navigate remote folders without FUSE, preview and confirm a disposable copy/check, observe live progress in Remotes, Jobs and Activity, close/reopen the WebUI, verify persisted history and stale banners clear, cancel an active disposable job, and test `ksu.exec` failure recovery. Archive screenshots and support evidence while redacting remote names and tokens. Actual testing here is not yet automated by the CLI runner.

### Release gates and outstanding work

After raw API tests pass, correlate source and installed binary with the actual build receipt, rerun startup diagnostics across multiple reboots, verify CE storage gate and eliminate remaining `start_error_other`, verify offline queued-edit conflicts/writeback recovery and remote data integrity, and perform independent Android WebUI/user-namespace FUSE checks. Then run CFS1/G01–G08 release qualification as defined in the repo; do not self-issue a release seal from these tests alone.
