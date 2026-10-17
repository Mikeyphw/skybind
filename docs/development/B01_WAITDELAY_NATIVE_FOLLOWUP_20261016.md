# B01-W2 — Native Termux Go package scheduling follow-up

## Observations (October 17, 2026 UTC)

- Failed full regression run: `26adffe087b341a6b25e8aa390f6873e`, 503.998 seconds; R0 BKX 9/9, chrootctl 5/5, R1 policy PASS; full Go regression **FAILED**, `mounts/lifecycle` and `opevents` emitted `exec: WaitDelay expired before I/O complete`. 29 Go packages passed, 2 failed, 2 no test files. Other previously failing packages (`paths`, `mounts/policy`) passed in this attempt.
- User executed the supplied source-bound, no-cache `-p 1` diagnostic for all four suspect Go packages: each **PASS**, exit 0, no WaitDelay. `go version go1.27.1 android/arm64`, source commit `7a1c8168fbc82603ce999ecc21d9ba791ce10779`; summary `build/evidence/go-waitdelay/summary.json`. This isolated evidence does NOT qualify the full test suite.
- Cause not established. Package scheduling contention is now a concrete experimental variable. Go WaitDelay indicates subprocess I/O closure failure, not a test assertion. Do not suppress the message, return success on failed Go tests, or clear old evidence.

## B01-W2 patch

Add `[targets.skybind_go.go] max_workers = 1` to the target-local Devtool resource policy. This makes the native Devtool GoRunner execute `go test -json -p 1 ./...` (instead of `-p 2`) while retaining event-based reporting and fail-closed qualification. This is deliberately scoped to Skybind Go; other Devtool targets and Android Github Actions are unchanged. Keep the existing fast source gate independent, and keep `r1-full-regression` mandatory for qualification. Add `tests/test_r1_go_runner_policy.py` to detect accidental policy regression.

## Native follow-up

From your patched Termux Skybind checkout:

```sh
python3 -m unittest tests.test_r1_go_runner_policy -v
# Confirm the exact emitted go test command shows -p 1:
devtool -r "$PWD" invoke r1-full-regression --target skybind_release
```

If the full native run still produces WaitDelay, run this **raw Go control** from the same shell, without modifying Devtool source:

```sh
go test -json -count=1 -p 1 -timeout=120s ./... > "$HOME/skybind-go-serial-native.jsonl" 2>&1
printf 'raw-go exit=%s\n' "$?"
```

If the source-bound native GoRunner fails but the raw control passes repeatedly, investigate Devtool launcher process group, file descriptor inheritance, environment and output-stream handling. If both fail, inspect Go 1.27.1 Android process lifecycle and Termux resource pressure/OS process kills with matching timestamps before attributing a source bug. Preserve the original failed run and serialized-run result separately. Failed full regression is not a PASS; pending GitHub Android builds and broker cross-UID acceptance remain open.

All Android application and instrumentation APK compilation must remain GitHub Actions-only. No device install, uninstall, reboot or data mutation is authorized by this patch.
