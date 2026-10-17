# B1-QW1: source-bound Devtool Go scheduling repair

Baseline: `b45ce65b3dfc3bb3bf3bc8576f371c9f61945059` (Skybind `main`, 2026-10-17). This overlay pins modified files by full SHA-256 (manifest schema 2). Reject changed sources rather than attempting an inexact merge.

## Changes

- Correct the stale `r1-full-regression` test to expect the authoritative B1-B `r1-identity-source`, while preserving the distinct nested transport and Android cloud-only policy gates.
- Declare `skybind_go.jobs.isolated-regression` as `read_only=false` because `go_all_packages.py` writes versioned receipt files under `build/evidence/go-regression-isolated/`.
- Give the four R1 Go-package testing jobs the same `skybind-go-build-cache` global reservation to serialize Go-heavy test execution when scheduling is explicitly parallelized.
- Add source assertions covering output classification, reservation parity and retained sequential defaults.

## Safety and limitations

- `workspace.scheduler.parallel=false` remains unchanged. This is **not** a concurrency activation.
- Go native diagnostics, uncached package acceptance, device exclusivity, hosted-only APK builds, R0/B1 source gates and release policy remain unchanged.
- The artifact validates source contracts only. It does **not** install an APK, enable the broker listener, perform device acceptance, qualify CI, or produce a final release seal.
- A Devtool `plan` output demonstrates concurrency eligibility, not actual safe Termux concurrent execution. Native Termux acceptance and EXO timing comparison remain future work.

## Follow-up on the user's own Termux checkout

```sh
devtool -r "$PWD" plan r1-full-regression --target skybind_release --workflow-parallel --workflow-max-workers 3 --json
# For actual source acceptance (serial by default):
./devtoolw r1-regression
```

The overlay does not run the latter exhaustive Go regression automatically, avoiding a potentially lengthy or platform-dependent package test during configuration repair.
