# SB-Q05P7 — Native diagnostics visibility and safe mount failure categories

## Evidence

The October 11 `/data/adb/skybind` export records a failed `mount.start` at
21:37:45–21:37:47 UTC. Its journal says `operation_failed`, and its existing
log contains only `operation=mount.start outcome=operation_failed`. The actual
provider stderr had been dropped by `linuxSpawner`.

The native `diagnostics.logs` operation returns `[]Entry` with RFC3339
`timestamp` and uppercase `level`. The WebUI assumed `{records: [...]}` with
`time_unix_ms` and `severity`, causing 0 visible records even when the daemon
log contained hundreds of records.

## Scope

- Adapt the WebUI log renderer to native arrays and legacy fixture envelopes,
  normalize timestamps/severity, and fail visibly on incompatible responses.
- Preserve known mount lifecycle errors in the RPC fault message and append
  a separate ERROR event to the private diagnostics log.
- Capture **only the last 4 KiB of stderr in process memory**, then report
  a closed set of failure categories. Raw stderr, user options, configuration
  and secrets are never written to WebUI logs or exposed over RPC.
- Forget the capture after mount startup succeeds or fails.
- Continue checking process identity and FUSE mount identity. No direct
  mount/unmount actions or changes to signed/qualified release gates.

A category such as `provider_permission_denied` is diagnostic evidence,
**not proof of the kernel/root cause**; unclassified stderr is explicitly
reported as `provider_stderr_unclassified` rather than guessed. Existing
failures cannot retroactively recover previously discarded stderr.

## Validation

`go test ./...`, `node tests/integration/test_q05p7_logs_truth.mjs`,
WebUI ES-module parse checks, and existing Q05 frontend tests. CI calls the
new native-log mapping test before candidate packaging.

All candidates remain unqualified. G01–G08 BLOCKED; seal NOT_ISSUED.
