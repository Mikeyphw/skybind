# Phase A3 — richer rclone job statistics, no mount requirement

This extends Phase A1/A2; no changes to frozen 57-operation catalog, socket permissions, mount management or offline/writeback paths. Existing `operation.events` event schema version **1** remains compatible. New `progress` fields are optional and sanitized; older consumers may ignore them.

Fields:

- `bytes`, `speed_bytes_per_second`, `eta_seconds` remain available.
- `total_bytes`: rclone's `totalBytes`; omitted if unknown (not estimated).
- `percent`: byte-derived `min(100, bytes/totalBytes*100)` only when total_bytes > 0; if total changes while scanning this is an estimate, not completion proof.
- `files_done`, `files_total`: rclone `transfers`, `totalTransfers`; these count transfers, **not checks or skipped files**. Zero is distinguishable from missing.
- `checks_done`, `checks_total`: rclone `checks` and `totalChecks`, available for check jobs as distinct counts.
- `errors`: rclone's error count; **not a retry count**.
- `retry_error`: rclone's `retryError` boolean; indicates rclone saw an error other than `NoRetryError`, not the number of retries.
- `transfer_retries`: numeric value only if the actual structured statistics contain `transferRetries`. **Standard rclone `core/stats` does not currently supply this**, so most real jobs will report an unknown retry count. Skybind does not fabricate one from the error count, log text or backoffs.

All rclone logs are parsed in memory and discarded except the above scalar numbers/booleans. No remote names, file paths, error descriptions, credentials, or raw logs are persisted to the operation event store. Numeric types, finite speeds, allowed ranges and known type/state schemas are validated. The JSON event feed remains bounded by the existing 512-event/512KiB durability policy. Progress snapshots are committed and emitted at most every 2 seconds per active run; terminal events are persisted at run completion.

The WebUI Jobs/Activity event panels render byte totals, percentage (only when known), completed/total transfers, errors and retry availability; they reconstruct a throughput sparkline from at most 24 recent progress events per run in the existing 96-record UI buffer. Unknown totals render indeterminate progress; the WebUI does not assume rclone can resume partial bytes after cancellation. After cursor gap, the authoritative `jobs.status` remains the source of state/cancellation truth.

Host tests are not Android device acceptance. Validate with a disposable copy/check job between unmounted remotes, inspect event replay, background/reopen WebUI, then verify terminal status. Avoid destructive sync/cancel of real offline edits. Reboot/startup acceptance is separate.
