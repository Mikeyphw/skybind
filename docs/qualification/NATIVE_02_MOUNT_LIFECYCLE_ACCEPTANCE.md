# NATIVE-02 — Native mount lifecycle acceptance

**Scope:** Android authenticated root bridge & UI. Personal APK not qualified.

## Source implementation

- New typed Binder preview methods: `previewStartMount`, `previewStopMount`, `previewRestartMount`, `previewReconcileMount`; plus `confirmMount`.
- Start uses daemon `mount.start.preview` proof retained exclusively in root process. Every action requires an explicit per-session root-service ticket (TTL 60 seconds, single use) and UI acknowledgment.
- Before confirmation, rechecks configuration revision; for named mounts also observes current daemon mount identity (observed/desired/PID). Unknown/foreign/stale input is rejected before daemon mutation.
- Stop/Restart call existing ownership-protected daemon methods; Reconcile calls bounded supervisor `reconcile`. No duplicate retry after ambiguous outcome.
- No generic privileged Binder RPC, raw shell, configuration mutation, sync, external broker, or automatic mount action on app launch.

## Proof and safety distinction

Only **Start** is protected by a daemon one-use preview proof. Other lifecycle actions are bound to short-lived, root-service-local tickets and a fresh preflight, but not to a daemon-issued one-use mutation proof. They remain subject to daemon FUSE ownership, writeback/stop and supervisor policy. This distinction is a release-audit obligation, not an accepted independent security guarantee.

## Qualification matrix (all OPEN until external evidence)

1. GitHub Actions builds matching app and AndroidTest APKs from the exact new source, using the existing stable signer, without disabling source-drift controls.
2. Pull back the installed pair and verify APK hash/signature matches the run artifact.
3. On a disposable configured mount: Start with fresh proof; Stop safely; Restart safely; Reconcile; compare to daemon mount.status.
4. Negative: stale config revision; foreign/stale/consumed ticket; wrong mount and session ID; root denial; SELinux denied; root-service death; daemon disconnect mid-run; writeback/busy/foreign FUSE mount; background/resume and app recreation.
5. Verify none of these operations occur on app launch, automatic reconnect, refresh, or tab navigation; confirm consent requirements; ensure no unexpected daemon root command scope.
6. Preserve Q16/Q17/R1 and personal module evidence as historical scope. Do not reuse prior nine-lane Android acceptance for the changed APK.

**Expected fresh evidence:** tested source SHA, workflow run and APK hashes, signer, device fingerprint, root manager, per-case positive/negative status, actual mount ownership, and receipt paths. Static tests are not substitutes for this matrix.
