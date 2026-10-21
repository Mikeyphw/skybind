# Skybind R1 abstract read-only consumer transport (SOURCE-ONLY)

## Evidence checkpoint

User-supplied real-device receipt `r1-pm-bridge-bf07ded28099404ea3b9183d4345c1c4.json`, source `7ba88071f6e3446316948c4789c80d33be7963ee`, reports `PASS_R1_ANDROID_TO_GO_PM_THREE_CASES_PLUS_FOUR_AGENT_NEGATIVES`: four named Android agent negatives; authenticated BKX PackageManager signer observation through the root Go channel; wrong signer denied; wrong Skybind authority UID denied; `pm_channel_qualified=true`. This **only qualifies the installed R1 Android-to-Go PM channel**, not BKX or chrootctl as live broker clients.

## What this milestone adds

- `brokeripc.AbstractConsumerSocket`: root-only, explicitly activated, bounded-concurrency Linux/Android ABSTRACT namespace endpoint `\0skybind-r1-consumer-gateway-v1`, avoiding the inaccessible root-owned `/data/adb/skybind` pathname ancestor. A socket-name collision causes startup failure, never a path fallback. Android SELinux may still deny connection; no SELinux policy changes or permissive mode are authorized by this overlay.
- Existing `brokeripc.Server` continues enforcing real kernel `SO_PEERCRED`, per-request app signer/process attestation (`AndroidVerifier` via the already device-qualified Android-to-Go PM channel), independently sealed `chrootctl` process attestation, precise remote/prefix/operation authorization, short-lived process-bound grants, identity rechecks and revocation. No new grant store or token issuer is created.
- `brokeripc.RequestOnce` gives independently deployed Go consumers a single-call, bounded client for the same versioned JSON request/response, with half-close framing. No credentials, tokens, URLs or arbitrary socket paths are stored in the client. Android Java/Kotlin consumers must implement equivalent framing independently.
- `brokerruntime.Gateway.StartAbstract` fails closed unless the PackageManager authority is **actually connected** and the installed-module verifier is canonical (`InstalledModuleAttestor` with non-substituted paths). Tests using injected fake authorities cannot start an external endpoint. Normal Skybind startup does not call it.
- Source Go real-socket tests exercise a root-owned socket with kernel credentials, no grant denial, an approved harmless JSON fixture read, remote and path traversal rejection, forbidden operation rejection, immediate grant revocation, wrong UID denial and listener teardown. Tests run with `sudo` on hosted Linux; Termux tests can skip root-only fixtures if the runner isn't root.

## Remaining distinct qualification gates

1. **Independent Skybind authority app-signing trust anchor** at the Go side, outside consumer-controlled JSON and outside the same unprivileged agent being attested. The authenticated PM channel alone does not prove the authority APK signing lineage to root.
2. **Live socket reachability on Android** for actual installed BKX app UID `10327` and live chrootctl process, including Android SELinux. Existing root-only filesystem socket implementation is *not* the chosen candidate for BKX because its parent `0700` path is inaccessible. Source tests do not establish Android SELinux permissions.
3. **Real BKX/chrootctl adapters** and a securely operator-approved, revocable token delivery path to the verified running client. Neither consumer is rebuilt, automatically switched to Skybind, or compelled to disable its native-rclone fallback by this source overlay.
4. **Typed read-only backend** and real scoped metadata receipt for the supported remote, without leaking private config, credentials or unrestricted filesystem content. The source fixtures return inert JSON only; they never contact actual remotes or backup repositories.
5. R1 end-to-end independent device acceptance with wrong-signer, wrong UID, SELinux, PID reuse, module seal mutation, grant expiration/revocation, remote/prefix escape, malformed request and concurrent client negative matrix. Until this passes, `available_external_capabilities=[]`, transport `NOT_IMPLEMENTED`, product/release=false.

## Build and qualification policy

`./devtoolw r1-consumer-transport-source` is a five-node source DAG. Hosted `skybind-source.yml` runs the targeted ordinary and sudo root Go tests. This change does **not** add or change an Android APK, installed module service or device instrumentation binary; it is not a production deployment. Historical four M3 device PASS scopes are preserved and no M2/M3 device tests are rerun. For source-only validation, no GitHub Android APK build is required. Do not promote the consumer-provider status because the PM channel and this source gate both pass.
