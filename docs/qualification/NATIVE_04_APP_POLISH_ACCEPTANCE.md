# NATIVE-04 — Full native app polish acceptance ledger

Baseline: exact applied **NATIVE-03 Complete Delivery** source-tree `71a13886bd7d31ea5170d638af5ada485c40542b`. This source-bound overlay does not promote an APK nor alter the previously approved personal module.

## Promise-by-promise audited implementation

| Roadmap promise | Implemented code / behavior | Executable evidence | Delivery |
|---|---|---|---|
| Home truthful root/backend status | Existing authenticated `LinkState`; daemon `runtime.status` validated boolean on-disk integrity and provider; no FUSE capability inferred | `native04_polish_gate.py`, `LiveReadGatewayTest` | SOURCE DELIVERED |
| FUSE/mount status & retry | Authoritative `mount.status`; optional bounded `mount.health` with exact mount identity and numeric retry; degraded/stale counts, no global FUSE claim | Gateway positive/negative health tests | SOURCE DELIVERED |
| Android network state | Only normal `ACCESS_NETWORK_STATE` permission, OS-observed validated/unvalidated status labeled as **Android**, not backend/provider reachability | Source gate permission and UI checks | SOURCE DELIVERED |
| Job progress / class / cancel | Lazy keyed configured/current/recent lists, compact bytes/speed/ETA, copy/check preview, blocked sync, owner-only cancellation unchanged | Existing jobs negative/source gates; `NativePolishUiTest` | SOURCE DELIVERED |
| Job receipts | Expand exact opaque run ID for operator lookup; never construct an unavailable file URL or pretend raw ID is a downloadable receipt | Native UI activity/receipt instrumentation | SOURCE DELIVERED (run ID; daemon has no report URL API) |
| Journal activity | Lazy bounded chronological entries, severity filters, human timestamps, readable names, expandable raw event/operation IDs, explicit replay gap | Native UI and presentation tests; event parser tests | SOURCE DELIVERED |
| BKX split & no accidental service | Explicit FGS start/stop, Off/Starting/Failed/Service observed/socket observed distinctions; peer socket is NOT BKX authorization; foreground root auto-connect still cannot start service | MainActivity, Agent and FGS source guard; UI state tests | SOURCE DELIVERED |
| BKX lifetime and notification truth | Persistent explicit keep-in-background preference; stop service on leaving app if preference disabled; Android notification enabled status reported independently | Source/semantics test, no implicit permission request | SOURCE DELIVERED |
| More diagnostics, privacy, About | Module runtime integrity, mount counts, APK versionCode/versionName, Android SDK, full local installed APK certificate SHA-256 on request, security/privacy; unavailable module version explicitly unavailable | `NativePresentation`, source and instrumentation tests | SOURCE DELIVERED |
| Browser retention / performance | Hoisted LazyListState; folder-scoped scroll reset and stable item keys, compact human sizes, no transfer write mutation | Existing browser tests and `native04_polish_gate.py` | SOURCE DELIVERED |
| Accessibility/large font/orientation | Navigation semantics, >=48dp key controls, vertically stacked mount/quick actions, scrolling views; 200% font and screenshot fixture tests | `NativePolishUiTest` | SOURCE DELIVERED (device screenshots pending) |
| Empty/offline/error states | Strict `failClosed` clears runtime/network-daemon proof and cached remote/job/mount state; explicit unavailable screens and gap warning | M1/M2 negative tests plus new runtime invalidity tests | SOURCE DELIVERED |
| No new unscoped bridge writes | Query allowlist only adds typed `mount.health`; existing one-use proof and session checks unchanged | Legacy M1/M2/M3/N03 and new mutation source gates | SOURCE DELIVERED |
| APK/build/signer/device receipts | This is intentionally a later NATIVE-05/06 release boundary, not an N04 code feature | Must run GitHub CI + actual root device | **NOT YET EXECUTED — release gate** |

### Qualification boundary

These rows mean the **source feature** is present; they are not assertions that the Android compiler accepted the APK or that a real device behaved correctly. Screenshots can only be taken and compared on a real Android instrumented target. The `NativePolishUiTest` captures authenticated and disconnected Compose image pixels and tests large-font semantics; device execution is pending. No current APK is approved by this overlay.

### Native Android acceptance run after applying overlay

1. Commit/push this new Skybind source. Trigger `.github/workflows/skybind-android-apks.yml` at that exact SHA and confirm hosted app+androidTest pair, same persistent signer, all jobs PASS.
2. Confirm/install only the same-source, same-signer APK pair via `scripts/devtool/ci_artifacts_device.py` with explicit `--install` when needed.
3. Execute the `NativePolishUiTest`, `NativePolishPresentationTest`, `LiveReadGatewayTest` on a selected ADB target; collect screenshot evidence for Home/Jobs/Activity/More and large-font/orientation; ensure no status-bar collision.
4. Run explicit BKX opt-in start/stop, notification-disabled and keep-in-background cases, root allowed/denied/reconnect, and stress-check 200-file Browser navigation and 100-event replay handling.
5. Refresh historical evidence status: Android source changed; do NOT reuse old device/installed-pair receipts. NATIVE-05/06 handles release signing and owner acceptance.
