# Phase A: operation events and resumable progress transport (source-only)

This personal-project API extension is **not** part of the frozen 57-operation CFS1 catalog. It does not claim device acceptance or release qualification. Android device tests are required after building/installing this change. No new remote-file mutation API is introduced here; existing `job.run` continues to require a separate preview proof, strict job registry and resource policy. All Phase A events are observational.

## Scope

- Stable **32-character IDs** for persisted job runs (`Run.ID`) and synchronous journal operations (`Record.ID`). `operation.status` remains authoritative, and accepted job launches refer to `job_run_id`.
- Private durable event spool: `/data/adb/skybind/events/events-v1.json` (0600), using the already-verified directory owner and no-follow atomic writes. Last event sequence survives restart; maximum **512** retained events, maximum **512 KiB** spool. Older events are removed; cursor gaps are explicitly indicated.
- Event types: `operation.started`, `operation.succeeded`, `operation.failed`, `operation.accepted`, `job.started`, `job.progress`, `job.cancelling`, `job.completed`, `job.failed`, `job.cancelled`, and `job.interrupted`.
- Numeric job progress currently exposes `bytes`, `speed_bytes_per_second`, `eta_seconds` when available. Totals, file counts and percentages are **not invented** when rclone does not provide them through the current runner. Progress events are coalesced to roughly once every 2 seconds; a final terminal state is persisted.
- After unexpected daemon restart, previously persisted `RUNNING` jobs become `INTERRUPTED` as before and the event extension emits a one-time interrupted event after attachment. No automatic transfer resume is claimed.
- Error events contain **no raw handler error**, remote path, mount name, stderr, credential or file name. They use fixed event names and phases. The event log never accepts unvalidated client-provided data.
- If the new event spool cannot be opened or its registration fails, the daemon **continues** with the existing mount and offline recovery; event API is unavailable and a sanitized warning is logged. Event write failure does not roll back an already executed mutation, and callers should fall back to `jobs.status` / `operation.status`. The poll response signals `degraded` if an append failed during this daemon lifetime.

## Typed RPC / embedded WebUI compatible poll

Operation `operation.events`, class `query`, additive allowlisted extension, served by the existing **same-UID Unix socket**. Embedded WebUI must continue to use its existing authenticated request bridge; do not expose a new public listener or unauthenticated rclone RC port.

```json
{"schema_version":1,"request_id":"client123","operation":"operation.events","class":"query","arguments":{"cursor":0,"limit":32,"operation_id":"","wait_ms":0}}
```

`limit`: 1–64 (default 32). `wait_ms`: 0–5000; a nonzero wait is bounded long polling, not an unbounded streaming socket. `operation_id` optional, otherwise match a hexadecimal journal or run ID (32 lowercase hex characters). `cursor` is the last *processed global sequence*, so filtered clients still advance past unrelated events. Response contains `events`, `next_cursor`, `oldest_cursor`, `latest_cursor`, `has_more`, `gap`, `cursor_reset` and `degraded`. If `gap=true`, obtain an authoritative status snapshot before proceeding. If `cursor_reset=true`, reset to `next_cursor` and re-query; do not infer historical events.

Sample event (illustrative, no real user data):

```json
{"sequence":42,"unix_millis":1790000000000,"operation_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","run_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","operation":"job.run","type":"job.progress","state":"running","phase":"transferring","progress":{"bytes":2048,"speed_bytes_per_second":256,"eta_seconds":4}}
```

`operation.accepted` links the synchronous journal operation ID to its job run ID, which the client can then use for filtered progress. Persistent operation IDs are not transferable bearer tokens: the existing privileged/same-UID and WebUI authentication boundaries remain mandatory. `operation.status` and `jobs.status` are authoritative on state after any gap or degraded feed.

## CLI

```sh
# Status snapshot
skybind events
# Follow all sanitized events as one JSON object per line
skybind events --follow
# Follow a particular job run, resuming from a prior cursor
skybind events --id aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa --cursor 42 --follow
# One-shot typed query, via existing CLI route
printf '%s' '{"cursor":42,"limit":20}' | skybind operations events --stdin
```

The JSON Lines follower exits automatically when a matching terminal event is seen and otherwise until interrupted. Client disconnects do **not** cancel jobs. Cancellation continues to use `operation.cancel` with the actual job run ID; `job.cancelling` means the cancellation signal was requested, **not** yet completed.

## Follow-up Phase A tasks

This first vertical slice does **not** yet wire Activity/Home progress presentation into the WebUI or implement SSE/WebSocket servers or an external SDK. A later Phase A overlay should consume `operation.events` from the existing embedded bridge with bounded polling and display live job progress, then add optional streaming support for other trusted clients. Mount/FUSE supervisor progress and M5/M6 offline tasks are not yet instrumented with per-task byte counters. Phase B covers mountless remote file mutations.

## Safety qualification

Required before device acceptance: exercise event polling from WebUI/CLI without a mount, prove start/progress/terminal sequences for copy/check/sync, cancel while active, reboot with running job, reconnect/replay after disconnection, force >512 events to observe gap, verify read-only offline write queue remains untouched, and run old filesystem regression batches. Source-only Go tests/vet/race and Android arm64 cross-build do **not** constitute device evidence.
