# M5 — Selective read-only offline snapshots (Personal Release)

**Scope shipped:** independently downloaded complete files, bounded recursive directory pinning, protected SHA-256 content-addressed storage, checksummed manifest, upstream checksum validation where supported, reboot persistence, stale/conflict detection, quota accounting, explicit Android Downloads export, manual unpin and garbage collection.

**Scope deliberately pending:** WebUI Keep Offline buttons and live download progress; automatic revalidation without a network; transparent FUSE offline fallback; offline writes, conflict resolution, and automatic eviction. The existing `offline` VFS profile does **not** guarantee complete downloads. Do not call this a transparent offline filesystem.

## Architecture and safety

- Root-only, narrowly typed `skybind offline` CLI; *no new daemon IPC command* and no modifications to the frozen 57-operation contract or existing FUSE engine.
- Pin source is resolved exclusively from an existing **named mount** in the validated registry. Caller cannot supply arbitrary command flags, paths, shell code, executable locations, or rclone config.
- `rclone lsjson --stat --hash` obtains file metadata, and `rclone copyto` downloads a complete file into `/data/adb/skybind/offline/objects/.download-*`. Files remain unpublished until transfer success, exact-size validation, local SHA-256, supported upstream MD5/SHA checks, and a second remote metadata check. If a remote exposes no supported hash, the manifest labels it `metadata+sha256` instead of claiming authenticated upstream content; both provider variants require real-device smoke testing.
- Published objects use content SHA-256 names and `0600` permissions in root-owned `0700` private directories. The manifest is atomically written via Skybind's existing `atomicfile` and checksummed; a corrupted manifest fails closed. A crash before publication leaves an unreferenced object; `offline gc` explicitly removes verified orphans and abandoned incomplete temporary downloads.
- The default offline physical-store quota is **8 GiB** (configurable 1–64 GiB); each file/directory request is bounded at **4 GiB**, recursive lists at **256 files**, and downloads reserve at least **512 MiB** free storage. Quota accounts for retained orphans until `gc`. There is **no automatic eviction**, especially not from rclone's separate dirty VFS cache.
- `status` verifies local content without network, and optionally `check` compares current remote metadata/hash. States: `AVAILABLE_OFFLINE`, `STALE`, `CONFLICT`, `UNAVAILABLE`. Pin commands are synchronous; no persistent `DOWNLOADING` UI state is claimed in this stage. `CONFLICT` means a locally corrupted/missing snapshot, *not* an offline write conflict.
- `export` is a user-initiated **separate copy** under Android's Downloads `/storage/emulated/0/Download/Skybind-Offline/<mount>/<path>`. It does not overwrite an existing file; it may be readable and writable by other Android apps, depending on Android storage permissions. Treat exported decrypted data as sensitive. The private source remains unchanged. Not a FUSE mount, not a synchronized folder.
- No credentials, remote endpoint, source filenames, or raw backend errors enter a new log or public sidecar; a root caller can request `offline list` and see their own private pin paths. Non-root and arbitrary RPC clients cannot invoke this command.

## Usage after installing a newly built Personal Release

Run the *new installed* Skybind binary via root from Termux (adjust the example mount name to your actual configured name):

```sh
SB=/data/adb/modules/skybind/system/bin/skybind
su -c "$SB offline pin safegdrive Documents/report.pdf"
su -c "$SB offline pin-dir safegdrive Documents/Important"
su -c "$SB offline list"
su -c "$SB offline status safegdrive Documents/report.pdf"
# While online; checks remote metadata for revision changes:
su -c "$SB offline check safegdrive Documents/report.pdf"
# Deliberate copy into Android Downloads (not synchronized):
su -c "$SB offline export safegdrive Documents/report.pdf"
su -c "$SB offline quota 4"    # GiB; refuses to shrink below retained bytes
su -c "$SB offline unpin safegdrive Documents/report.pdf"
su -c "$SB offline gc"         # explicit orphan and incomplete-file cleanup
```

Relative paths are relative to the mount's configured remote root; no leading slash, `..`, double slash, or colon. `pin-dir` is limited to 256 files and 4 GiB per request; already-pinned files remain durable if a later file in the batch fails.

## Android smoke checklist (not run in CI)

1. Keep a working module ZIP available for rollback. Apply overlay with Devtool, build `./devtoolw personal-release`, install the ZIP, then reboot if required by KernelSU.
2. Pin a short document. Verify `list`, `status`, SHA-256 and export; open the exported copy in an ordinary Android app.
3. Disable Wi-Fi/cellular (airplane mode). Run `offline status` again and open the already exported file. `offline check` cannot establish remote freshness offline; stored bytes still verify.
4. Reboot offline and repeat the local status and ordinary-app read. Verify unpinned paths return `UNAVAILABLE` and no file is silently synthesized.
5. Interrupt a larger pin, recover with `offline gc`, and confirm no incomplete file was published.
6. Restore the network; change a remote revision, run `offline check` and verify `STALE`, retaining local bytes. Ensure `mount.stop`/`restart` retains M1 writeback protections.
7. Repeat at least one file for bclone and NewFuture, including a backend without upstream hashes, and note `verification` truthfully.

## Follow-on M5 UI phase

A WebUI Keep Offline workflow requires a deliberately reviewed extension to the frozen typed API or a separately authenticated transport with equivalent safety. Do **not** tunnel privileged filesystem commands through generic RC, existing job operations or client-side shell execution. Until that integration is developed and validated, M5 remains **CLI functional, WebUI pending**. Offline writes are specifically reserved for M6 and are not implied by public exports.
