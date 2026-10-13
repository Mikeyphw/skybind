# M5B — Offline snapshots in the Skybind WebUI

Status: SOURCE_IMPLEMENTED / ANDROID_DEVICE_NOT_TESTED / PERSONAL_RELEASE. Does not modify the formal CFS1 gate state or claim transparent offline FUSE access.

## UI

Open **Mounts → [mount card] → Offline files**. Enter a **relative path under the mount's configured remote root**, then choose **Keep file** or **Keep folder**. Only one offline copy/export task runs at a time. Its bounded, transient status is shown in the panel; a full-file or recursively selected folder may take minutes. Operations continue in the root daemon if you close the WebUI, but a daemon shutdown interrupts them. Task status is in-memory (last eight tasks), while successfully verified pinned objects and the manifest persist on disk.

The control also lists pins for that mount, allows on-demand local **Verify**, explicit two-step **Export** to Android Downloads (public, not synchronized), explicit **Unpin** (manifest only), and a 1–64 GiB offline store quota (default 8 GiB). No automatic deletion of verified pinned files, dirty VFS data, or orphan cleanup is added. There is **no background auto-pin** or offline-write synchronization.

The UI shows pin metadata as *stored*, not implicitly as locally verified. **Verify** reads the local content and checks SHA-256. If it fails or times out, availability is unverified. Remote freshness is not proven by the local check. Export enforces a local checksum again and creates a separate public copy without overwriting files already in Downloads. Export copying is cancellable and removes partial output on failure.

## Backend boundaries

- Uses the existing authenticated /api/v1/* and KernelSU-embedded typed WebUI bridge; no root-shell command construction, WebUI execution path, or generic file-serving HTTP endpoint.
- Eight explicitly allowlisted `offline.*` operations: `list`/`status`/`tasks` (query), `pin`/`export`/`unpin`/`quota` (run), `cancel` (cancel). Strict request parsing; the offline store validates mount names, relative paths, remote identities, quota and private storage.
- These are optional PERSONAL extension operations. The **original canonical 57-operation CFS1 API remains byte-for-byte unchanged** and the optional extension is intentionally not counted as one of those historic entries. The WebUI detects absence by trying a typed query and reports unavailable if the matching new daemon isn't installed.
- Copies/exports enqueue in a single bounded async worker (30-minute timeout). Status requests do not wait for long transfers. Cancellation is best effort; a directory may already have independently verified and persisted some files. The WebUI stops polling when hidden; the task does not stop merely because the UI is closed.
- Journal success for `offline.pin`/`offline.export` means **request queued**, not transfer finished; inspect `offline.tasks` for the actual outcome. Worker errors are sanitized (no backend URL, credentials or stderr).
- `offline.cancel` cancels the worker's context and aborts rclone copy or copy-to-Downloads in progress. `offline.unpin` intentionally does not delete content-addressed objects. `offline gc` remains an explicit root CLI maintenance command and should not be run during an active transfer.

## Known scope limits

- No transparent fallback to pinned files through FUSE when remote goes offline. Pins are accessible by `skybind offline status`, `list`, and explicit `export`.
- No file picker in the panel yet; users type a validated remote-relative path.
- The task manager does not persist pending jobs across daemon restarts; interrupted task state is unknown until the saved manifest is checked. Incomplete `.download-*` orphans can require a supervised root-CLI `offline gc` after confirming no worker is active.
- No precise live byte progress; task status reports running/succeeded/failed/cancelled and completed file count. This avoids introducing an unverified transfer progress protocol.
- Device WebView, root-manager behavior, real provider pin/export and airplane-mode functionality require testing on the device; source tests alone do not establish them.

## Validation

Run `go test ./...`, `go vet ./...`, `go test -race ./internal/offline ./internal/daemon ./internal/control`, Android ARM64 cross-build, `node --test tests/webui/*.mjs` and `scripts/devtool/check_q05p4_webui_esm.sh`. Full source guards and overlay inventory digests are enforced at application.

## Device acceptance

1. Apply overlay and build Personal Release. Keep previously working module ZIP.
2. Open Mounts → Offline files on a named configured mount. Pin a small test file. Check `SUCCEEDED`, list entry, then Verify -> `AVAILABLE_OFFLINE`.
3. Enable airplane mode. Verify must remain `AVAILABLE_OFFLINE`; Export must create a separate readable file in Download/Skybind-Offline. It must not make the FUSE mount automatically read offline.
4. Try invalid paths (`../secrets`, `/etc/passwd`); ensure no file is pinned. Start a larger pin then Cancel. Verify that incomplete data is never listed as successfully pinned.
5. Confirm export needs a second click and existing output files are not overwritten. Unpin then confirm other pins persist. Confirm stopped mounts and mount recovery remain unchanged.
