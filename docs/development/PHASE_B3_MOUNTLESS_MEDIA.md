# Skybind Phase B3 — Mountless media transfers, folder creation and guarded file moves

**Exact-pinned, source-only Devtool overlay** for the checkout after Phase A1/A2/A3 + B1 + B2. The installed Android module and device startup configuration remain unchanged until an intentional build/install. No FUSE, CE gate, cache or offline-writeback source files are modified.

## Implemented

- `remote.media.preview` / `remote.media.start`: managed **folder upload and download** jobs using configured remotes directly. Local source/destination is **only** under `/storage/emulated/0/Download/Skybind-Transfers/<subfolder>`; create the parent directory first. No arbitrary root-owned local paths, no symlinks within the inspected tree, no remote-root folder transfers, no overwriting pre-existing destination files (`--ignore-existing`). Both operations use Phase A's persistent job progress, history and cancellation. Individual-file upload/download picker and Storage Access Framework are **not** provided in this first implementation.
- `remote.mkdir.preview` / `remote.mkdir.run`: create **one remote folder** with an expiring single-use proof tied to rclone config; requires a readable parent folder, checks for an existing destination before execution. It is a bounded synchronous metadata call (success/failure), not a continuously streaming transfer.
- `remote.file.move.preview` / `remote.file.move.start`: **single-file rename or move within the same configured remote**. Requires `lsjson --stat` to confirm source file, readable complete destination parent, destination absence, config and source-size fingerprint, explicit second confirmation, and `moveto --ignore-existing`. Directory moves and cross-remote move are refused. Rclone moves the source only after a successful transfer. Caution: external changes between preflight and execution remain possible; a skipped move in a concurrent collision may be reported as completed by rclone. Validate completed moves on-device before trusting this for important files.
- Remotes WebUI has panels for these actions; proof tokens remain in memory only. Stale async preview responses cannot restore proof after form change. Upload/download/move jobs appear in existing A1–A3 progress views.
- CLI forms `skybind remotes media-preview --stdin`, `media-start --stdin`, `mkdir-preview --stdin`, `mkdir-run --stdin`, `move-preview --stdin`, `move-start --stdin` accept bounded JSON on standard input.

## Important safety boundaries

No destructive sync or deletion. No overwriting destination objects. No recursive directory move. Do **not** use paths with queued offline writeback. Moving a file is intrinsically destructive because the source disappears when successful, so test using disposable files. Rclone's `--ignore-existing` means skipped existing targets preserve the source; it is not an atomic create-if-absent guarantee across all providers. Android root-namespace and filesystem symlink checks reduce risk but cannot make a multi-step external rclone process immune to concurrent filesystem mutations. The UI file move confirmation never promises a reversible action.

## Local setup

```
su -c 'mkdir -p /storage/emulated/0/Download/Skybind-Transfers'
```

A chosen relative folder, for example `outgoing/photos`, must exist before an upload. For a download, it may be created by rclone beneath the existing exchange root. Note that `copy` copies folder **contents**, not the folder's own basename.

## Install source overlay

```
B="$HOME/Downloads/SKYBIND_PHASE_B3_MOUNTLESS_MEDIA_V1_20261014.zip"
unzip -p "$B" apply.sh | bash -s -- "$B" "$HOME/Code/skybind"
```

The wrapper verifies bundled checksums, invokes Devtool with its global `-y` flag, and deletes the downloaded bundle only after a successful transaction. Failed preflight/validation invokes Devtool rollback. It does not rebuild/reinstall/reboot Android.

## Verification

Host/source checks include full Go suite, vet, targeted races, Android arm64 compile, WebUI JS tests, HTML parity, frozen operation catalog, proof one-use/config drift, symlink/path traversal, move collision, and source-drift negatives. Those checks are not Android device acceptance.

After an intentional build/install, use disposable remote folders. Test read-only browsing, create folder, small uploads/downloads, reconnect progress view, cancel a disposable copy, rename one disposable file and verify both endpoints. Capture support/diagnostic evidence if the embedded WebUI fails; do not report release qualification from host tests alone.
