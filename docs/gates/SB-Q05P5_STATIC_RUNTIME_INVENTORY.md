# SB-Q05P5 — Static FUSE helper runtime authority

## Device finding

KernelSU bclone candidate built from the Q05P4 WebUI fix reported:

`{"provider":"","ready":false,"reason":"invalid manifest inventory","provenance_available":false,"provenance_valid":false}`

The installed `runtime.provenance.json` contains exactly the two executable members
`system/bin/rclone` and `system/vendor/bin/fusermount3`. This is the reviewed
NewFuture v1.75.0 static-helper delivery mode, reused by bclone; the independent
Q04 provider/build evidence and Q05 package manifests verified both bytes.

The Python full candidate builder had already corrected its minimum-member count
to two (SB-Q05P1), but the **Go** on-device `integrity.Decode` path still required
at least three entries. It failed before any provider hash could be checked.

## Narrow remedy and preserved security

- Accept an inventory with **2..66 members**, not 3..66.
- Continue to require exact `Skybind` / `arm64` / allowed-provider identity.
- Continue to require *both* the fixed engine and FUSE-helper paths.
- Reject traversal, absolute/symlink paths, invalid hashes, and missing members.
- Continue to verify every listed file on disk using `O_NOFOLLOW`, exact SHA-256,
  exact size, regular-file checks and non-world/group-writable mode.
- Do not create a fake `libfuse*.so`, disable provenance verification, substitute
  a provider, change upstream pins or grant a release seal.
- Test both `newfuture` and `bclone` static-helper manifest acceptance, missing
  mandatory member and tampered-file rejection.

`go test ./...` is already executed on the CI host before Skybind's Android/arm64
binary is compiled; the two new Go regression suites therefore gate newly
assembled candidates automatically. The Devtool overlay also runs focused tests.

## Next evidence boundary

This overlay modifies **Skybind's native Go runtime validator**, so it requires a
new complete Android/arm64 candidate compiled and installed through KernelSU.
The existing installed module is not repaired by applying a Devtool source overlay.
Re-run `skybind runtime-status` after the rebuilt module is activated and inspect
any new failure reason. A source test or `ready=true` alone does not prove actual
FUSE mounting, cross-app access, full device qualification or a final seal.

**G01–G08 BLOCKED; final seal NOT_ISSUED.**

## WebUI: show actual native runtime failure cause (V2)

The Q05P4 WebUI successfully connected and exported Doctor evidence, but its Home
page replaced the native `runtime.status.reason` with the generic message
"Bundled runtime is not operational." The Runtime page similarly displayed a
generic authority string in its main notice. Users could not distinguish the
observed `invalid manifest inventory` from a missing helper or digest mismatch.

V2 retains `runtime.status` as a read-only, fail-closed authority and displays
its exact bounded reason in Home attention, Home runtime details, Runtime notice,
and Runtime technical metadata. Backend request failures become visible on Home
instead of leaving a stale "Checking" state. Diagnostic text is inserted with
`textContent`, not HTML, strips control characters, and is length-limited.
Healthy provider status does not turn unknown FUSE device qualification into
independent release approval. The WebUI tests cover the real native response
`{"ready":false,"reason":"invalid manifest inventory"}`, plus missing
reasons, SHA mismatches, and healthy statuses. Candidate CI enforces the tests.

This is a source repair, not a WebView retest. Rebuild a complete candidate,
reinstall via the root manager after checking the updated ZIP, and re-run
`runtime-status` and the WebUI. No device gate or release seal is promoted.
