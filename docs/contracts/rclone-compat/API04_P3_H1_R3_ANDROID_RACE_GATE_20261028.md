# Skybind API04 P3-H1 R3 — native Go race-gate host policy

**Complete replacement** for the failed P3-H1 R2 artifact, still pinned to pushed P3 source commit `ebf056968a9dac6d6921c1fb73c6b8e449a716e8`.

Devtool run `7f15e8e908014a60b4b5fd8954a84064` passed the native Go suite but the artifact validator attempted `go test -race` under Android/ARM64, which the installed Go compiler reports as `-race is not supported on android/arm64`. Devtool correctly rolled back 22 touched and four added paths, with `rollback_verified: true`.

R3 retains all R2 native guarded stop proofs, exact 57+2 strict catalog validation, tests, root ownership, query/mutation socket partition, and transactional source pins. It corrects only the host-qualification policy: the native Android/ARM64 lane runs three complete uncached iterations of the five relevant packages, explicitly records that race was NOT run and remains open; vetted native Linux/macOS/FreeBSD/Windows hosts run `go test -race` unchanged. Cross-target, unknown or malformed host environments fail closed. Any test failure remains fatal.

Android repeated tests do **not** prove data-race freedom. Independent race detector evidence on a supported host, Devtool transaction acceptance and real installed-device SELinux, FUSE/reboot/lifecycle tests remain open. No external consumer files changed and mutation stays default disabled.
