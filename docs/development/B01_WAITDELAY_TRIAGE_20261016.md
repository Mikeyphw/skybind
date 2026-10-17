# Skybind B0/B1 — Termux Go WaitDelay incident and recovery

Source evidence: Devtool run `c569f0dab44a460e85d2a49b05fd8140`, native Termux, ended `failed`, 2026-10-17 00:48:46 UTC. Its GoRunner invoked `go test -json -p 2 ./...`. Four packages reported `exec: WaitDelay expired before I/O complete`: `internal/mounts/lifecycle`, `internal/mounts/policy`, `internal/opevents`, `internal/paths`. 27 other Go packages passed; 2 had no tests. Devtool correctly surfaced test failure; the R0 BKX, chrootctl and R1 policy stages were skipped due to the original full-suite dependency.

## What is and is not known

Go's own `cmd/go/internal/test` emits `*** Test I/O incomplete 1m0s after exiting.` when a test process has exited but its output pipe does not close by the configured WaitDelay. This is a process-I/O failure, **not proof of a failed Go assertion**. The paths package has no process-spawning tests, so there is not enough evidence to blame Skybind's rclone subprocess lifecycle. Possible contributors include host process termination, inherited file descriptors, Go/Termux runtime behavior, or cross-package concurrency. **The exact cause is not established.** Do not silence or reclassify the error.

## Workflow repair

- `r0-compat` now runs just the independent BKX/chrootctl source contracts.
- `r1-source` runs those two plus R1 policy Go tests; all three are independent Devtool DAG nodes. **Fast gate only.**
- `r1-full-regression` runs the full native GoRunner suite **and** the fast source gate. The complete workflow still fails when any Go package fails, and therefore remains required before marking B0/B1 fully source-qualified.
- Android APK builds remain exclusively in GitHub Actions; no Android build workflow is modified by this patch.

## Termux procedure

Run fast source feedback:

```sh
devtool -r "$HOME/Code/skybind" invoke r1-source --target skybind_release
```

Isolate the 4 observed packages, with `-p 1`, no cache, a 120-second Go test timeout, a 180-second per-package wrapper budget, and raw JSON logs kept in a private 0700 directory:

```sh
cd "$HOME/Code/skybind"
python3 scripts/dev/diagnostics/go_waitdelay_probe.py --stop-on-failure
python3 -m json.tool build/evidence/go-waitdelay/summary.json
```

Inspect `summary.json` and the corresponding `.jsonl` in the private output directory. To probe a single package:

```sh
python3 scripts/dev/diagnostics/go_waitdelay_probe.py --package ./internal/paths
```

If a standalone package reproduces it, inspect `go version`, `go env GOOS GOARCH`, Android process/kernel logs for terminations around the test and any surviving descendants before making runtime changes. If standalone all pass, retry full suite serially from Termux (`go test -json -p 1 -count=1 ./...`) and compare raw Go against Devtool GoRunner to localize concurrency vs orchestration. Do not treat a successful isolated probe as the full gate.

After understanding and resolving the failure, run:

```sh
devtool -r "$HOME/Code/skybind" invoke r1-full-regression --target skybind_release
```

No automated release/production approval is implied by these workflows. Historical Q/Android device evidence is preserved; the original failed Devtool run stays failed.
