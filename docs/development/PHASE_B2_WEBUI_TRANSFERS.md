# Skybind Phase B2 — WebUI direct remote copy and check

**Source-only Devtool overlay** pinned to the Phase A1, A2, A3, and Phase B1 checkout. It does not rebuild, replace, or restart the installed Android module. It deliberately does **not** modify mount, CE, FUSE, or queued offline writeback implementations.

## Features

- The existing authenticated, mountless `provider.remotes` / `provider.browse` browser selects configured folders. Use **Use open folder as source/destination** or the folder action menu. Remote roots, file entries, malformed paths, and ancestor/descendant overlap are refused on the UI and again by the authoritative backend.
- `remote.transfer.preview` (copy or check) returns a *single-use*, config-bound, 120-second authorization proof, stored in page memory only. Any source/destination/kind change discards it; stale async responses cannot restore it. This is a **policy preview**, not a file-by-file diff.
- Explicit native confirmation before `remote.transfer.start`. Copy skips existing objects (`--ignore-existing`) and may create new destination objects; check is read-only. No delete, sync, move, overwrite or remote-root transfer.
- The Remotes screen now shows A3's replayable live progress (bytes, totals, percentage where known, files, checks, speed, ETA, throughput), including after leaving and returning. Jobs and Activity retain their progress panels.
- Cancellation controls now rely on actual `jobs.status.runs`, not the nonexistent `jobs.status.jobs`. Only a backend-confirmed `RUNNING` run can be cancelled, using `operation.cancel` with its run ID. Successful cancellation does not undo earlier completed file copies.
- No credentials or proofs persisted to browser storage. No untrusted markup rendered from backend paths; user content uses `textContent`.

## Apply in Termux

```sh
B="$HOME/Downloads/SKYBIND_PHASE_B2_WEBUI_TRANSFERS_V1_20261014.zip"
unzip -p "$B" apply.sh | bash -s -- "$B" "$HOME/Code/skybind"
```

The wrapper verifies archive hashes and applies the **single exact-pin overlay** using Devtool (`-y` global flag). On failure the ZIP stays in Downloads and Devtool rolls back the failed transaction. It is removed only after successful apply. Do not attempt to apply directly over a pre-B1 checkout.

## Validation / acceptance

Source checks: Go full suite, `go vet`, all WebUI JS/Python tests, frozen API catalog, targeted races, Android ARM64 cross-build; focused proof-invalidation/replay/cancellation/parity tests; archive SHA256 and source-drift negatives. These are **host/source** checks only, NOT embedded KernelSU/Android device acceptance.

After an intentional module build/install, use only **disposable remotes/folders**, never folders with pending offline writeback. Open WebUI → Remote browser, choose two nonroot folders, run a read-only `check` first; test a small `copy` with known destinations and verify existing files were preserved. Observe progress through refresh/view switching. Do not cancel an important production transfer for testing. No module rebuild required just to apply source.
