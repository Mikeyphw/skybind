# Skybind Phase B1 — mountless remote management

**Source-bound, not an installed Android build.** Designed for the user's latest Skybind Oct 14 snapshot with successfully applied A1 and A2. Phase A3 is required; the installer will apply the bundled original A3 source overlay first *only if* exact post-A2 source hashes are detected. Otherwise, it expects post-A3 source and refuses source drift.

## Included

- Existing `provider.remotes` and mountless browser remain unchanged. New authenticated `remote.list` and `remote.stat` queries work independently of FUSE mounts, with configured-remote and path validation, output/time limits, no raw shell.
- `remote.transfer.preview` with `{"kind":"copy"|"check","source":"configured:folder","destination":"configured:folder"}` yields single-use proof valid for 120 seconds, bound to full rclone config hash (never revealed).
- `remote.transfer.start` supplies same fields plus `"proof"`; returns durable `RUNNING` job ID. `copy` adds the rclone `--ignore-existing` flag, never overwrites existing destination objects; `check` is read-only. Both use the same A3 live progress events, cancellation (`operation.cancel` with run ID), `jobs.status`, and replay.
- All endpoints must be configured remote folders (nonempty subpaths), not local/root or overlapping same-remote ancestors. No destructive sync/move/delete/mkdir in this first stage; no spontaneous uploads or scheduled job creation.
- CLI supports `skybind remotes ls REMOTE:PATH`, `skybind remotes stat REMOTE:PATH`, `skybind remotes transfer-preview --stdin`, `skybind remotes transfer-start --stdin`.

## Install source overlay in Termux

```bash
B="$HOME/Downloads/SKYBIND_PHASE_B1_MOUNTLESS_REMOTES_V1_20261014.zip"
unzip -p "$B" apply.sh | bash -s -- "$B" "$HOME/Code/skybind"
```

Source-only (Devtool) apply; no module build, module replacement or reboot. A3 is included as an optional source-only prerequisite. An applied A3 overlay is skipped by exact hash; any other checkout drift is rejected. If either overlay fails, the wrapper preserves the original download and Devtool rolls back its failed transaction; a previously successful prerequisite is not rolled back automatically.

## After intentional module rebuild/install — safe disposable test

```bash
su -c '/data/adb/modules/skybind/system/bin/skybind remotes ls alpha:tmp'
# Preview a check (no writes); pipe JSON into CLI. Capture returned proof.
printf '%s\n' '{"kind":"check","source":"alpha:tmp","destination":"beta:tmp"}' | su -c '/data/adb/modules/skybind/system/bin/skybind remotes transfer-preview --stdin'
# Start uses same JSON plus the returned proof:
printf '%s\n' '{"kind":"check","source":"alpha:tmp","destination":"beta:tmp","proof":"<RETURNED_PROOF>"}' | su -c '/data/adb/modules/skybind/system/bin/skybind remotes transfer-start --stdin'
su -c '/data/adb/modules/skybind/system/bin/skybind events --follow'
```

Replace example names only with *configured disposable test folders*. A `check` can fail if contents differ; that is a normal verification outcome, not evidence of an API defect. For any copy test choose a disposable destination, confirm expected files and no overwrite, avoid directories involved in queued offline writes. The eventual A3 WebUI Jobs/Activity view can display transfer events without a mount. B2 is planned for direct WebUI transfer controls, upload/download, previewed rename/mkdir/move/delete, and carefully reviewed sync/conflict safety.

## Validation (host/source only)

Full `go test ./...`, `go vet ./...`, targeted `go test -race` (provider, jobs, daemon, control), all WebUI JS suites, frozen catalog/parity tests, Android arm64 build, negative source drift and bundle hashes. No on-device verification or release qualification claimed.
