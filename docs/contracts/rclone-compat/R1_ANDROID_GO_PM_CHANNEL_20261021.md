# R1 Android-to-Go authenticated PackageManager channel

**Qualification:** source-only Go protocol PASS; installed BKX Platform PackageManager observation `PASS_R1_BKX_PLATFORM_PM_OBSERVATION_ONLY` on October 21, 2026, GitHub run 39532482009, artifact 12316097658, source `627fce0285deb07e8f2252c65a2f86fec5ccf6f7`. The NEW socket channel is **NOT YET DEVICE-QUALIFIED** and neither consumer has externally granted broker access.

## What is implemented in this consolidated overlay

1. The unprivileged Skybind **app** now hosts `R1PMBridgeAgent` only while `MainActivity` is visible. It attempts to attach to a preexisting, explicitly activated ABSTRACT Android local socket. It never starts the root listener, issues grants, executes an rclone command, or starts BKX/chrootctl. It uses Android's real PackageManager to resolve `com.mikeyphw.bkx.android`, its exact installed UID ownership, and its installed APK signer DER. An unknown package, UID, unsigned/multisigner package or malformed query is rejected. Android package visibility lists only BKX, not `QUERY_ALL_PACKAGES`.
2. `brokeridentity.PMBridge` is a Go `PackageAuthority` implementation. It can only listen under an explicit privileged invocation. The listener pins the **Skybind authority app UID and exact SELinux context** independently; it authenticates Android kernel `SO_PEERCRED` and `/proc/PID/{stat,status,attr/current}` with process start-time before and after each request. Each lookup sends 256-bit CSPRNG challenge nonce and verifies returned nonce in constant time, UID, package, bounded certificate DER, canonical JSON (unknown and duplicate fields rejected). `PlatformPackageAttestor` then checks the DER signer against the operator-approved BKX signing certificate digest, without accepting a value provided by BKX or the PM agent as a grant pin. The socket has no filesystem pathname so it avoids a false assumption about crossing a root-only `/data/adb/skybind` parent directory. This bridge is read-only and cannot issue tokens.
3. `cmd/skybind-r1-pm` is a **separate root diagnostic binary**. It is not the installed module runtime. It requires explicit `--skybind-uid`, `--skybind-context`, `--bkx-uid`, and `--bkx-signer` pins. It fails closed when the authority app is absent, UID/SELinux invalid, BKX signer mismatches, or process incarnation changes. It prints machine JSON only; its highest qualification is `PASS_R1_AUTHENTICATED_PM_CHANNEL_ONLY` with `consumer_broker_qualified=false`, `grants_issued=false` and no M2/M3 retests.
4. Dedicated GitHub `skybind-r1-pm-bridge.yml` builds only a source-bound Android-arm64 Go diagnostic and a SHA-256 manifest, not a production module. Existing `skybind-android-apks.yml` builds the app and test APKs; hosted compilation remains mandatory. `r1_pm_bridge_device.py` verifies both artifacts and the installed APK pair against the SAME exact source SHA and runs **seven** device checks: four Android instrumentation negative tests (unknown package, nonexistent UID, malformed challenge nonce and unrecognized request fields), followed by **three** Go authority-channel cases: approved signer, wrong signer rejection, wrong authority UID rejection. `--restart-skybind` is required to establish three independent authority sessions; BKX/chrootctl are never launched or backed up. All receipts remain false for external provider and release. Go unit tests additionally cover repeated challenge replay, wrong UID/package, corrupt or duplicate JSON, oversized payloads, wrong SELinux, changed process UID and PID-start time.

## Security requirements and limits

- Operator must independently approve **Skybind authority UID + SELinux label** and **BKX UID + signer DER SHA-256**. Never read those from a consumer request or auto-trust values recorded by a probe. Changed authority UID or security context blocks the connection; changed BKX signer blocks authorization without forcing a Skybind rebuild. The PM agent is restricted by kernel UID; this first version does NOT independently establish Skybind app's installed signing lineage inside the Go process. That additional trust-anchor verification remains a hard release gate.
- Android's SELinux policy may deny this abstract-socket connection even with correct pins. Only a real-device receipt can demonstrate reachability. Do not weaken SELinux or root-owned private directories in order to pass it.
- `brokeridentity.InstalledModuleAttestor` (chrootctl) is still source-tested and binds a live PID to a sealed executable. A running, authorized chrootctl process **has not yet been observed**. Its separate process-attestation device acceptance remains required.
- `brokerruntime.Gateway` policy, scoped 5-minute grants, revocation, per-PID incarnation verification and existing read-only consumer socket remain source-tested. This package does **not** connect those to a real BKX or chrootctl adapter; they have no authenticated live consumer requests. Neither installed consumer is rebuilt or switched from native rclone. The earlier `ConsumerSocket` parent 0700 directory accessibility issue remains **open**, and the production listener stays disabled. Do not claim whole R1/external provider/release qualification from the PM-channel PASS alone.
- Never use a self-asserted consumer JSON, `pm path`, process names, package version, APK digest, root UID alone or embedded signing history as an authorization decision. Do not copy rclone credentials, contact backup archives, or run any M3 device lane because of this overlay.

## Source and device execution

Source gate: `./devtoolw r1-pm-channel-source`. Existing source gates and Go regression remain mandatory. New hosted Go diagnostic workflow and hosted Android APK workflow must BOTH run against exact matching source HEAD before running the device suite.

In Termux, measure Skybind app's UID/SELinux independently (without trusting BKX or app-supplied claims):

```sh
su -c 'pm list packages -U | grep -F io.github.mikeyphw.skybind'
su -c 'pidof io.github.mikeyphw.skybind'
# If active, inspect /proc/<real PID>/attr/current as root.
```

After independently approving the pins, for new hosted APK run `$APK_RUN_ID` and new R1 Go diagnostic run `$GO_RUN_ID`:

```sh
python3 -B scripts/devtool/ci_artifacts_device.py --run-id "$APK_RUN_ID" --expected-sha "$(git rev-parse HEAD)" --serial emulator-5554 --install
python3 -B scripts/dev/android/r1_pm_bridge_device.py --apk-run-id "$APK_RUN_ID" --go-run-id "$GO_RUN_ID" --expected-sha "$(git rev-parse HEAD)" --serial emulator-5554 --bkx-uid 10327 --bkx-signer "$BKX_SIGNER_SHA256" --skybind-uid "$SKYBIND_APP_UID" --skybind-context "$SKYBIND_APP_SELINUX" --restart-skybind | jq
```

`--restart-skybind` explicitly restarts **only** the Skybind UI three times for the chosen tests; no installed module or BKX application changes. Without `--restart-skybind`, the automation now fails closed before retrieving artifacts, because it cannot reliably start each independent authority session. The final receipt requires correct state **and** mutually consistent `pm_channel_authenticated` / `bkx_signer_approved` flags per case, four named instrumentation successes, and no grant or provider-qualification claims. Machine receipt flags are conservative: a source PASS, artifact build PASS, and PM-only PASS do not confer BKX/chrootctl process attestation or external grant authority.

## Overlay audit and acceptance hardening (2026-10-21)

Audit of the original consolidated ZIP found that Android instrumentation negatives existed only in the source and were **not run** by the three-case device runner. This was not an end-to-end qualification. The repaired ZIP adds the four actual Android instrumentation cases to the automated run, requires explicit UI reconnects between each Go diagnostic case, checks positive and negative machine-receipt flag consistency, fails closed if the diagnostic overclaims grant/provider status, and tests missing/malformed/forged Android instrumentation reports offline.

**Total scoped device cases after repair: seven** (4 Android denial tests + 3 authenticated-Go scenarios); all remain **PENDING DEVICE ACCEPTANCE** until the hosted pair, hosted Go binary and real device return matching authenticated receipts. The Skybind authority APK signer independent trust anchor, chrootctl process attestation, scoped broker client transport and real grant/revoke acceptance remain separate, unqualified gates.
