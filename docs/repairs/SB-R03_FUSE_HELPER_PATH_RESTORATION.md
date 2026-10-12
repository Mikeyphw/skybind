# SB-R03 — Nexus FUSE helper PATH parity (source-only repair)

## Evidence-based comparison

The supplied 2026-10-09 Rclone Nexus original configured `provider.RuntimeEnv`
so the bundled NewFuture `system/vendor/bin/fusermount3` directory was **first**
in the child rclone process PATH. Skybind's `linuxSpawner.Start` replaced this
with `PATH=/system/bin:/system/xbin`, excluding its own verified helper.

The installed Skybind diagnostics reported `MOUNT_START_FAILED` with the
safe hint `provider_stderr_unclassified`. This does **not** prove the helper
was the root cause; the hint deliberately omits raw provider stderr.

## Minimal restoration

- Only the FUSE mount child receives the canonical module helper directory as
  its first PATH entry and the canonical private state root as HOME.
- No executable lookup through an untrusted inherited PATH or any fallback to
  Termux/system rclone/fusermount, remote download, or user-supplied paths.
- The existing `runtimeauth.StatusCanonical().Ready` precondition and digest
  checks remain mandatory before child startup.
- Existing mount proof, PID/start-time/executable verification, mountinfo ID,
  foreign mount refusal, and secret-safe stderr categorization are unchanged.
- The old Nexus WebUI has not been installed over Skybind; WebUI parity remains
  separately testable, and the native bridge/log fixes are retained.

## Required next gate

Devtool source validation is not Android device evidence. Rebuild and install
an **unqualified** candidate from the repaired source, then verify real FUSE
readiness and exact target-app visibility using an owned mount. If mounting
still fails, collect the current Doctor/diagnostics export to isolate other
causes (provider remote, FUSE permissions, timeout, SELinux, namespace).
No G01–G08 promotion; final seal `NOT_ISSUED`.
