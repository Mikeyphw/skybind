# SB-API05-UI01 — Mount wizard preset-duration compatibility (2026-10-29)

## Observed issue and source root cause

In the embedded KernelSU WebUI, the **Add mount → Performance → Review mount** step produced `INTERNAL: Unsupported duration; use 30s, 15m, 24h or 7d`. The displayed Balanced profile included Go-native strings such as `120h0m0s`, `5m0s`, `1m0s`. `internal/mounts/policy/policy.go` formats preset duration options with Go `time.Duration.String()`. The wizard's `module/webroot/model.js` local checks accepted composite durations but `module/webroot/bridge.js` `seconds()` accepted only a single unit. The bridge rejected the payload before sending a native `config.validate` request; no mount mutation occurred.

## Fix and guarantees

The embedded bridge now accepts nonnegative, bounded composite Go/rclone duration fragments (`ns`, `us`, `µs`, `ms`, `s`, `m`, `h`) and standalone day/week units (`d`, `w`), along with numeric seconds, blank and `off`/`0`. It converts to integer seconds for the existing typed native API and rejects negative, malformed or overflowed values. It changes neither the daemon nor mount authorization, config schema, API-04 gateway, BKX, or actual device lifecycle. The local editor validator's existing composite-duration grammar is compatible with this fix.

`tests/webui/test_duration_bridge_profiles.mjs` covers seven built-in presets, the observed 120-hour value, fractions, zero, malformed inputs and overflow. The existing typed bridge and VFS UI tests are also mandatory in the Devtool validation. Full Go tests/vet remain source gates. Android WebUI instrumentation and a real mount preview are **not** claimed passed by the source tests.

## On-device verification after applying the Devtool overlay

1. Restart/reopen Skybind's root manager WebUI so it loads the updated installed `module/webroot/bridge.js` bundled by the appropriate deployment process. Updating the repo alone does **not** update the installed module.
2. Open **Add mount → Performance**, choose **Balanced** and confirm it keeps profile-generated values. Select **Review mount**. A valid review should not show the duration format error.
3. Do not apply/start a real mount solely to test duration parsing. An approved disposable mount can be used later for the separate API-05 lifecycle gate.
4. If the same error persists, verify the deployed WebUI bundle version and reproduce with a fresh UI session; do not disable validation or SELinux.

**Status:** implementation candidate; actual Devtool receipt, installed-WebUI repro and real API-05 lifecycle evidence pending.
