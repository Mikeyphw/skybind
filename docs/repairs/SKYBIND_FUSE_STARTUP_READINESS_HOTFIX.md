# Skybind — Android FUSE startup readiness hotfix

## Evidence and scope

The 2026-10-13 device support ZIP reported `FUSE readiness/mount identity not observed (provider_stderr_unclassified)`. A subsequent root probe showed `rclone lsjson` succeeds and `fusermount3` 3.16.1 can create temporary read-only FUSE mounts with and without `--allow-other`. Readiness was observed at approximately 1.75 and 1.50 seconds respectively. The existing Skybind mount engine allowed only 20 observations spaced 100 ms apart (roughly two seconds), leaving little margin for RC and VFS startup or scheduler load.

This makes an insufficient readiness window plausible, but **not proven**. The temporary probes did not exercise Skybind's full custom mount/VFS options, authenticated RC transport, or production namespace.

## Changes

- Wait **at most 10 seconds** for the original verified provider process and its FUSE mountinfo identity. Check every 100 ms and return as soon as ready.
- Abort observation if the original process disappears or its start ticks/executable change; never accept a mount belonging to a different process.
- On failed readiness, send SIGTERM only if the same process identity still exists. This avoids signalling a recycled PID. Untrusted output remains suppressed; only existing sanitized categories surface.
- Go tests simulate a mount appearing after more than 20 polls, an unobservable process and a mount that never appears. Unit tests use injected short deadlines; the production delay stays 10 seconds.

No provider binaries, helper, mount configuration, FUSE unmount path, VFS cache, pending writes, WebUI control catalog, supervisor backoff, or source lock are modified. There is **no automatic force unmount or cache cleanup**.

## Validation

Tested from the provided 2026-10-13 source snapshot: full `go test -count=1 ./...`, `go vet ./...`, race tests for lifecycle, Android ARM64 cross-compile, and 100 repeated timing-test runs. The overlay validates the same on application. Actual device recovery must be confirmed after building/installing a personal module ZIP.

## Device acceptance (don't risk pending writes)

1. Apply the Devtool overlay; run `./devtoolw personal-release` and install the built KernelSU ZIP, preserving the previous working ZIP for rollback.
2. With `safegdrive` idle and no pending upload, use WebUI **Start** and confirm RUNNING; use a normal non-root file manager to open a harmless existing file.
3. Use WebUI **Restart** only with a confirmed clean writeback state; confirm the mount returns. Avoid Stop/Restart if upload telemetry is unavailable.
4. Reboot when convenient; let the existing supervisor recover the mount. Record observed time and whether it mounted.
5. If Start still fails, export a *new* Skybind Doctor support ZIP, including the time and mount name. Do not delete the VFS cache or force unmount. The failure may instead be caused by a custom VFS option, provider early exit, authenticated RC or mount namespace differences.

**Not claimed:** existing device mount failure definitively diagnosed or repaired without a new installed-build test.
