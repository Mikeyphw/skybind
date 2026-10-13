# M5C — Verified Offline Views (Personal Release)

## Goal and implementation boundary

An original rclone-owned FUSE mount cannot have individual read failures intercepted by Skybind's supervisor. Blind bind mounts, provider configuration swaps, or modifying the FUSE implementation could conceal dirty writeback and violate the safety invariants introduced in M0–M4. **M5C deliberately does NOT claim transparent same-path offline FUSE fallback.** That remains pending, subject to source-backed provider evaluation and real-device qualification.

Instead, this iteration offers a useful **explicit per-mount offline view for other Android apps**. The user selects **Publish offline files view** on a mount's **Offline files** panel, then confirms that files will be copied publicly and consume additional storage. Skybind validates *every* pinned file before copying into a fresh directory below:

`/storage/emulated/0/Download/Skybind-Offline-Views/<mount>/snapshot-<UTC>-<random>/`

The same operation is available to root via `skybind offline view-publish <mount>`. It is allowed through a new explicitly typed `offline.view.publish` WebUI operation, outside the unchanged historical 57-operation catalog. It is processed asynchronously with the existing offline task/cancel UI.

### Safety and lifecycle

- The remote provider is **not contacted** during publishing. A successfully pinned snapshot can be used when disconnected.
- Pin integrity is checked by SHA-256 and byte length before publication; the remote-identity binding must still match the configured mount. Copies are hashed again while being written.
- All pins for the selected mount must validate. No successfully named snapshot is published when any pin is corrupted, stale-identity, missing, oversized, or cancelled.
- A new snapshot directory is created every time. Nothing is overwritten. Previously published copies are retained (users must remove them manually in their file manager when no longer needed).
- The temporary staging directory is randomized and only atomically renamed to its final name upon full verification. On error it is removed; never automatically remove private pinned objects or pending VFS cache data.
- Only fixed Android Downloads destinations are permitted in production. File and directory creation is descriptor-relative with `O_NOFOLLOW` to reject symlink substitution. No arbitrary paths, shell commands, or new root daemon are exposed.
- The public view consumes **additional storage**; it checks free capacity and a 512 MiB reserve before copying. Android Downloads permissions and POSIX read-only bits vary by device and do **not** provide tamper resistance. A public copy can be modified by another app, and is *not* synchronized to the remote.
- The same source/private store and 57-operation security boundary are preserved. No FUSE restart, data-plane mutation, or background sync is introduced.

### Test plan

1. With the M5B module running, pin two small files under the same mount from the WebUI.
2. Use **Publish offline files view**, confirm, and wait until the queued task succeeds. Browse the returned Downloads path using a non-root file manager.
3. Enable airplane mode, check those files are accessible at the **view path**, and verify their contents.
4. Verify original cloud mount behavior is unchanged. **Do not assume the original mount path has offline fallback.**
5. Unpin or corrupt a test pin and verify a new publish refuses without creating a final snapshot folder. Restore the pinned test file using normal pinning.
6. Test cancellation mid-copy, Wi-Fi reconnect, Stop/Restart, and a normal KernelSU module reboot. Existing private pinned bytes and original mounts must remain independent of public view copies.
7. Public snapshots contain plaintext. Do not publish sensitive remote files unless you intentionally want them readable from Android Downloads.

### Explicitly pending

- Same-path transparent offline reads via the original rclone mount. Requires a provably safe data-plane extension or an independent remount design accounting for mount identity, dirty cache, online/offline switching, Android namespace propagation, and access control. Not implemented in M5C.
- Writable offline sync and revision/conflict journal, M6. Not implemented in M5C.
- Android device validation. Go, WebUI, and Android compile tests cannot validate Android's shared-storage or FUSE behavior on the actual phone.

### Rollback

If M5C is undesired, revert the Devtool commit or restore the previous personal release ZIP. Existing private pins persist. Published Downloads copies are standalone files and can be deleted separately through your file manager.
