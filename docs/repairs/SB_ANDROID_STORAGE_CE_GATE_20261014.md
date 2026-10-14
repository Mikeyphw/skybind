# Skybind Android CE-storage startup deferral

## Evidence
Root service showed a Skybind daemon socket at ~19 seconds uptime, Android boot-completed at ~55 seconds, and user-0 CE storage / full mountpoint path first ready at ~276 seconds. Prior reboot attempts were blocked with catch-all `start_error_other`. This correlation motivates a narrow pre-spawn guard but does not establish that every startup failure had this cause. The root namespace FUSE probe observed no FUSE mount in the captured 13–344 second window; this does not establish FUSE health outside that namespace or after capture.

## Change
- The canonical lifecycle Start() only, for `/storage/emulated/0/...`, reads the bounded, fixed Android property `sys.user.0.ce_available` before verifying the mount destination. Only exact `false`/`0` defers, never missing/unknown/error. No provider process is spawned for this condition.
- The supervisor treats `ErrAndroidUserStorageDeferred` as a pre-spawn 30-second readiness deferral, not a provider failure. It consumes neither five normal retries nor two post-exhaustion probes and does not accept network events as storage-unlock proof. Existing real failures remain charged.
- Audit outputs a fixed `RECONCILE_STORAGE_DEFERRED` reason, with hashed mount name, no raw paths/provider output. 
- Explicit Stop, status ownership, policy evaluation, writeback, credentials and bounded-recovery behavior are unchanged.

## Qualification boundary
Source-only regression/race/vet and Android arm64 compile. This does not claim install/device verification, a clean first-attempt boot or that all `start_error_other` defects are solved. No Android module is built or installed by applying this overlay.

## Evidence to collect after deploying a candidate
An early-boot JSON log spanning unlock should show `RECONCILE_STORAGE_DEFERRED` without increasing attempts until `ce_available=true`; subsequent real Start should mount successfully. Compare with read-only diagnostic and HYBRID FUSE/integrity batches. Beware earlyboot root namespace FUSE false negatives.
