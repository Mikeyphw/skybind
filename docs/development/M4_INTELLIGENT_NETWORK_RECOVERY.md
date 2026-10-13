# Skybind M4 — Intelligent network recovery and battery efficiency

**Track:** Personal Release following applied M0/M1, M2, M3. Formal CFS1 not changed or issued.

## Design: one existing supervisor, no additional daemon

The KernelSU service still starts the same `skybind daemon`. A small netlink
`NETLINK_ROUTE` socket listens for kernel link, route and address notifications.
Each event is an *untrusted wakeup hint*, **never** evidence of online access,
an authenticated connection, an unmetered network, or charging state. The
existing `policy.SampleAndroidFacts` and per-mount `policy.Evaluate` path
continues to make all start decisions. If Android or SELinux disallows the
netlink subscription, operation continues with bounded periodic checks.

- First supervisor reconcile: after approximately **10 seconds** of daemon startup.
- Pending/degraded/retrying mounts and reconciliation errors: periodic **30 seconds**.
- All mounts healthy/explicitly stopped or no configured mounts: periodic **90 seconds**.
- Network-link/address/route notifications: coalesced in a one-slot channel,
  **3-second** settling delay and **15-second** event throttle. Bursts cannot
  produce an unbounded work queue. The actual network settle threshold
  configured for a mount remains enforced independently.
- Existing scheduled-job `Tick` continues every **30 seconds**, separately
  from less-frequent healthy mount reconciliations.
- No wake locks, background app, network polling process, external Android
  broadcast permissions or shell commands added.

## Retry and policy safety

Network notifications can advance **only** a previously policy-deferred
(`ErrResourcePolicyDeferred`, pre-spawn) check. Actual provider/FUSE failures
preserve their bounded attempt count (maximum five) and exponential backoff;
exhausted budgets are never reset by a reconnect event. The optional persisted
`deferred` field in `retry-v1.json` is backward-compatible with prior state.
Explicitly stopped mounts stay stopped. Unknown connectivity/metering or
unproven charging/battery state must still fail the existing network/resource
gates for mounts that require them. Existing device-specific boot/network settle
values, Wi-Fi/unmetered requirements, charging-only and minimum-battery limits
are unchanged and remain authoritative.

All supervisor audit entries are still deduplicated, categorized, and sanitized;
route events and raw connectivity details are not logged. This change does not
alter VFS dirty-cache protection, FUSE ownership checks, root IPC, provider
credentials, mount paths, or the existing 57-operation control contract.

## Validation carried out before distributing the overlay

- `go test -count=1 ./...` and `go vet ./...`.
- Targeted race tests for supervisor and daemon scheduler.
- Kernel event coalescing and debounced policy wake-up; provider failure
  backoff immunity; persisted policy deferral; explicit-stop immunity.
- Timed event-recovery test and fallback when netlink is unavailable.
- Android ARM64 compile (`GOOS=android GOARCH=arm64 CGO_ENABLED=0 go build -buildvcs=false`).
- Existing M2/M3 WebUI model checks, source-bound overlay validation.

## Device smoke test (still required)

1. Keep the previous working Personal Release ZIP for rollback. Apply overlay
   and build/install the M4 personal candidate when convenient.
2. Observe Skybind after boot; pending enabled mounts should recover normally.
3. Toggle Wi-Fi with a **disposable**, non-writing mount; confirm recovery after
   the network returns. Do not force-detach FUSE or delete VFS caches.
4. Test `wifi`/`unmetered`, `charging_only` and battery thresholds: a blocked
   mount must not start until its configured restrictions are proved satisfied.
5. Confirm explicit Stop stays stopped across network toggles and reboot.
6. Cause a **disposable** genuinely failing provider startup: real failures
   must still be bounded and must not be retried rapidly by network flaps.
7. Confirm an unavailable kernel notification source does not prevent the
   periodic supervisor from reconciling mounts.
8. Verify existing WebUI, performance, safe Stop/Restart, ordinary-app file
   access and resource usage during idle use.

**Scope not claimed:** no immediate notification of captive-portal validation,
no guaranteed instant recovery across Android vendors, no new Android
power-management exemptions, and no confirmed device energy benchmark yet.
Event notification availability and actual power benefit require device checks.
