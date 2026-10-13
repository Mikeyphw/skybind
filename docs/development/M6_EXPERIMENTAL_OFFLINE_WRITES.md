# M6 — Experimental offline write journal (personal build)

**Scope delivered:** explicit, root-private durable queue of modified copies of already-pinned files; public editable drafts; local SHA-256 sealing, checksummed atomic journal, bounded size and storage, remote revision comparison, conflict/unknown reporting, and confirmed uploads ONLY to distinct remote-copy paths. The M5 pinned snapshots, rclone FUSE mount and existing provider source remain unchanged.

**Safety rule:** NEVER modify or overwrite the original remote object, including if a revision check reports `MATCH`. Rclone's `lsjson` revision check is not an atomic compare-and-swap. A separate remote copy is placed under `<configured remote>/Skybind-Offline-Edits/<32-hex-id>/<original-basename>` with `copyto --immutable`. Such provider operations are not a universal transaction/atomic no-clobber guarantee; the unique path and immutable flag reduce the risk. Manual reconciliation is required. Remote copy commands also refuse read-only mounts.

## Workflow (WebUI)

1. Pin the original remote file using **Keep file**. Offline edits require a locally checksum-verified base.
2. Select **Edit offline** on its pin row, then confirm that an **unsynchronized PUBLIC editable draft** will be created in Android Downloads under `Skybind-Offline-Drafts/<mount>/<relative-path>`. Do not do this for confidential documents unless you accept this exposure.
3. Edit and save the *draft file*, not the root-private pin or the live remote-mounted path, using an Android file editor with appropriate Downloads access. Android scoped-storage/editor behavior varies; use an editor that can write the file.
4. Select **Queue edited draft**. Skybind verifies the original pin has not been corrupted, validates the drafted file, stores an immutable 0600 content-addressed copy in private write storage, and atomically persists its ledger. No network access is required to stage.
5. Inspect the **Offline write queue**. **Compare remote revision** returns `MATCH`, `CONFLICT`, or `UNKNOWN`. `MATCH` is observational, **not a write lock**. Missing remote checksums produce `UNKNOWN` rather than false certainty.
6. If you want to upload, use **Upload separate remote copy** then **CONFIRM**. The original remote file is never the destination. Manually inspect and merge the uploaded separate copy on the provider. This is not automatic synchronization.
7. An interrupted/cancelled/upload-error state may be `UPLOAD_INDETERMINATE` (task `REVIEW_REQUIRED`). Do not retry blindly: the copy may have arrived. Both the private queued content and its ledger remain for examination. No automatic upload after reconnect is attempted in this phase.

## CLI (root only)

```sh
SB=/data/adb/modules/skybind/system/bin/skybind
su -c "$SB offline write-draft safegdrive Documents/report.txt"
# Edit the generated Android Downloads/Skybind-Offline-Drafts/... file with an editor.
su -c "$SB offline write-stage safegdrive Documents/report.txt"
su -c "$SB offline write-list"
su -c "$SB offline write-check <id>"
su -c "$SB offline write-upload-copy <id> --acknowledge-separate-copy"
```

## Security and recovery

- Fixed root-private directories `offline/writes` and `offline/writes/objects`; both 0700, write objects 0600; checksum journal published with the existing `atomicfile` mechanism. Existing pinned content and VFS cache are not touched or garbage-collected by M6.
- Root-only CLI, narrowly registered typed WebUI operations with the existing peer/authenticated bridge. The historic 57-operation CFS1 catalog remains unchanged. No arbitrary user filesystem paths, destination paths, shell, or generic rclone commands enter the WebUI protocol.
- Public drafts are plaintext and outside Skybind's integrity boundary; edits are hashed on stage. Stage refuses symlinked leaves and directories. The private queue survives restarts and refuses corrupted ledger or object bytes.
- Maximum edited file size: 128 MiB; maximum queued logical edited bytes: 1 GiB; at most 64 ledger entries; preserve at least 512 MiB free. No automatic queue purge or deletion of pending data. A manual backup/reconciliation process is needed before clearing indeterminate or historical edits.
- Remote copy verification returns `remote-hash-verified` only if a matching provider SHA-256 hash is available. Otherwise `size-only-unverified`: transfer success is not a cryptographic end-to-end attestation. A failed or uncertain operation retains its state and source for review.
- The separate-copy upload is an explicitly user-requested network operation. It does not automatically monitor Wi-Fi, charging, or network policy, and will fail offline.

## Deliberately pending

- Automatic reconnect upload queue processing, durable protocol for reset/repair after indeterminate outcomes, and merges or updates of the original remote file.
- Transparent FUSE offline write fallback and conflict-free versioned in-place writes. The original path stays rclone-owned.
- Android device tests for editor permissions, public Downloads paths, airplane-mode edits, interrupted uploads, rclone provider differences, and WebUI behavior. Local test/ARM64 compilation cannot certify device behavior.

## Device smoke tests

1. Keep an installed working module backup. Pin a small test file and create/edit its draft in airplane mode.
2. Stage it while offline, verify `write-list` shows `QUEUED`, reboot and confirm persistence.
3. With network disconnected, `write-check` must report `UNKNOWN`; reconnect and expect `MATCH` for an unchanged checksum-capable remote.
4. Modify the remote original from another device and expect `CONFLICT` from `write-check`.
5. Confirm separate-copy upload, then inspect new remote path. Verify the **original remote bytes did not change**.
6. Interrupt another test upload: queue entry must become indeterminate/review-required, with no automatic re-upload.
7. Restore/install the prior KernelSU ZIP if the new feature affects normal mounts; private queued edits remain separate from the binary release.
