# Skybind M6B — Reconnect review and conflict recovery

**Track:** Personal Release (optional CFS1 gates unchanged)  
**Baseline:** M6 experimental offline writes (exact source-bound Devtool overlay)  
**Feature state:** Local/remote metadata review implemented; automatic upload and in-place reconciliation deliberately **not implemented**.

## Why this exists

M6 durable private edits are never replayed automatically. M6B adds a **read-only review pass** of the existing edit journal to help determine what to do after Android reconnects. Reconnect events are hints, not connectivity proof. Skybind can neither guarantee remote availability nor atomically lock a remote object during metadata inspection.

## Workflow

1. Keep a verified file offline, create a public editable draft and stage it into the private journal using the M6 controls.
2. Open **Mounts → Offline files**. Select **Review edits after reconnect** to start one bounded read-only background task for that mount.
3. Optionally enable **automatic reconnect review** in that panel. It is disabled by default and survives restart in a root-private, checksummed settings file.
4. Android network event/recovery-timer hints can initiate a review when opted in. At most one offline task executes at once, and automatic reviews are throttled to no more than one start every 5 minutes. The existing supervisor is reused; no new background daemon or foreground Android app is added.
5. Inspect the most recent timestamped review snapshot and take a deliberate action. Uploading a separate copy still requires the existing two-step acknowledgement and immutable unique destination; no review submits uploads.

## Status meanings

| Status | Meaning | Safe response |
|---|---|---|
| `MATCH` | Size, modtime and provider hash still match the pinned base *at inspection time*. | Decide whether to upload a **separate** immutable copy after explicit confirmation. **Not** an atomic lock or permission to overwrite. |
| `CONFLICT` | Original remote revision differs, or a separate destination has mismatched size/hash. | Keep local edit, inspect the remote and reconcile manually. |
| `UNKNOWN` | Remote metadata unavailable; absence is never inferred. | Wait for stable connectivity or inspect remote independently. |
| `LOCAL_CONFLICT` | Staged local bytes, mount binding, or recorded remote destination identity fails validation. | Repair/inspect manually; nothing is uploaded. |
| `REVIEW_REQUIRED` | Separate destination exists at the expected size but cannot be verified with SHA-256. | Inspect the destination manually; no retry is permitted. |
| `VERIFIED_REMOTE_COPY` | **Previously attempted** unique separate copy has a provider-reported SHA-256 matching the immutable staged object. | Journal is changed to `UPLOADED_COPY` only after successful validation and durable write; original was never targeted. |
| `COPY_RECORDED` | Earlier M6 upload result already recorded as a separate copy. | No new remote operation is initiated. |

The latest report lives in a root-private, checksum-protected `writes/review-v1.json`. Its timestamp is informational, not a durable proof that the original has remained unchanged. The opt-in is persisted separately as `writes/review-settings-v1.json`. A corrupt setting or journal causes fail-closed behavior. No filenames, remote tokens, credential text, or contents are written to supervisor logs by this feature.

## Hard boundaries

- No automatic uploads, retries, overwrites, deletions, merges, or in-place FUSE writes.
- No remote write caused by `ReviewQueue`, UI `offline.write.reconcile`, or network event callbacks.
- Indeterminate destinations are probed **only** at the deterministic unique path derived from the edit ID and basename; arbitrary journal-provided paths cannot redirect metadata probes.
- Only a matching size **and remote-reported SHA-256** allow promotion from `UPLOAD_INDETERMINATE` to `UPLOADED_COPY`. Hashless or unsupported providers require manual review.
- Context cancellation stops a review without publishing a partial result. A failed or disconnected probe never resets an upload state to `QUEUED`.
- Frozen 57-operation original catalog remains unchanged. New `offline.write.review`, `offline.write.reconcile`, `offline.write.auto-review` operations stay in the restricted offline extension with strict argument validation and existing authenticated transport.

## Device acceptance (not yet performed)

- After installation, stage one small text edit. Review online, then with networking disabled: the report must show `UNKNOWN` and never sync remotely.
- Re-enable Wi-Fi; with automatic review off, verify no automatic review runs. Enable it and verify a bounded review appears after network recovery, without uploading.
- Modify the original remotely and verify `CONFLICT` appears while the staged local edit survives.
- Simulate/intercept an uncertain separate-copy upload. Without SHA-256, it must remain review-required; with matching remote SHA-256 it may safely be recorded as a verified **separate** copy.
- Test manual Stop/Restart, mount availability, pinned snapshots, cancellation, and prior release rollback.

## Remaining M6 work

Actual remote merge, automatic resolution or true same-path offline FUSE writes require separate design and device tests. The safer personal-project default remains manual separate-copy reconciliation.
