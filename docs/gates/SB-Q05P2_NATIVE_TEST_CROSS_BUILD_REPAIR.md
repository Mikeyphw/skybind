# SB-Q05P2 — Native test execution vs Android cross-compilation

## Observed failed CI run

GitHub Actions `38113466115` reported a failure in **Compile static Go Android/arm64 Skybind native executable** after provider input download and Go installation. The failed-step summary does **not** contain the compiler stderr, so the precise original CI error is unverified.

## Independently reproduced source-level defect

The prior workflow set `GOOS=android GOARCH=arm64 CGO_ENABLED=0` at the job step level and executed `go test ./...` within that step. On Linux/amd64 this attempts to **run** Android/arm64 test executables on the host, producing `fork/exec ...: exec format error`. This reproduces using the same checked-in source with a local Go compiler.

## Bounded repair

1. Run all Go tests on the GitHub Linux/amd64 runner with `GOOS=linux GOARCH=amd64 CGO_ENABLED=0 GOTOOLCHAIN=local GOWORK=off` and selected Go **1.27.2**. Use `-count=1` to ensure execution instead of caching results.
2. In a separate step, cross-compile `./cmd/skybind` with `GOOS=android GOARCH=arm64 CGO_ENABLED=0`, verifying build metadata. No Android test binaries are executed on Ubuntu.
3. Preserve Q04 evidence inputs, NewFuture official prebuilt strategy, package comparison, selected pins and all existing evidence constraints.

## Qualifications NOT granted

This is a source/CI configuration fix. Until the **new GitHub Actions run** succeeds and its evidence is inspected, the complete candidate workflow remains unverified. Even after a successful candidate build, real device tests, independent approval, G01–G08 and final signing remain outside this patch. **Final seal: NOT_ISSUED.**
