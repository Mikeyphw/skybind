# Skybind: bounded auto-start recovery after Android boot

Status: source repair, **not** installed or device-validated; no formal qualification.

## Real-device evidence

October 13-14 supervisor audit history: multiple `start_blocked` attempts, twice `retry_budget_exhausted` after five attempts, and subsequent recovery in a later boot/runtime state. The later `RUNNING_NO_AUTOSTART_FAILURE_IN_WINDOW` verdict only covered samples taken after recovery; it did not negate earlier failures. The underlying provider/FUSE failure reason was redacted and remains unknown.

## Repair

- Preserve the original five normally backed-off start attempts. After the fifth real failed start, defer a **first** recovery probe for five minutes. If that fails, defer a **second and final** probe for fifteen more minutes. At most 7 provider start attempts are possible for an uninterrupted unhealthy desired mount, including daemon restarts. Ordinary reconcile cycles and network hints may not reset or expedite exhausted retry budgets.
- Persist the additional probe counter and fixed-category failure diagnosis into the existing private `retry-v1.json` without altering existing secrets, mounts or old persisted records. Previously exhausted v1 records without `recovery_probes` deserialize to zero extra probes; if their old `next` deadline is past, the first recovery probe can happen on the next periodic reconciliation. No implicit modification of desired mount state.
- Classify actual failure strings into a strict list of fixed tokens. Neither raw provider text, credentials, remote paths, nor mount names are stored in the new retry fields, audit events or supervisor health reasons. Last safe category is retained on exhausted/cooldown states.
- Preserve explicit user Stop, Android resource policy, off-line deferrals before spawn, process/mount identity checks, fixed built-in runtime executable, and dirty writeback protection. An unavailable/invalid retry-state file is not silently reset. A long-term real failure still produces permanent exhausted state after two probes; operator intervention may be required.
- Successful observed RUNNING clears retries/probes; manual state changes do not automatically happen.

## Validation

Host source tests: `go test -count=1 ./...`; `go vet ./...`; `go test -race -count=1 ./internal/mounts/supervisor ./cmd/skybind`. No device reboot, Android release build, module reinstall, or formal qualification was performed by this source repair. Android installation requires a later intentional build and installation decision.
