# Skybind R1 — operator-owned batch security acceptance

## Source and scope

Based on the uploaded clean Skybind snapshot at commit `56fe4e24e1cd1839b8005d5bca0bbc0852f9b09a` (`fix(r1): accept validated native rclone size JSON metadata`). The gateway keeps its existing authenticated PM bridge, approved root policy, canonical sealed chrootctl executable, Linux process attestation, abstract handoff and read-only broker. No BKX APK/module modification required.

The operator starts the *new hosted gateway binary* through the source-verifying v4 launcher, enables Skybind's visible BKX bridge, then enters `acceptance GDDavys` in its interactive root console. That explicit command is the only acceptance trigger. It runs the positive chrootctl metadata read; negative remote and operation attempts each using an actually issued, delivered grant with an intentionally narrower approved scope; then an attested-live-process grant-store suite including operation, remote, wrong-peer, absent-token, revocation and expiry denial. The Go gateway produces a root-only JSON receipt at `/data/adb/skybind/r1-security-acceptance/` and a redacted one-line report. No tokens are output or written.

**Truthful authority boundaries:** first three tests are real installed chrootctl -> gateway Unix socket exchanges. The remaining six use the actual production grant store and a live verified module process, but do not replay an Android app socket. An explicit `bkx_negative_socket_qualified:false` and `release_qualified:false` remain; the test also does not assert external-provider qualification. If any case fails, state is BLOCKED, with a specific bounded reason and no optimistic coverage. This is device engineering evidence, not approval to release.

The companion evidence collector reads the newest root security receipt, newest previously recorded installed-identity and transient module-device receipts, and writes one private report under the Termux user's home. It explicitly distinguishes earlier operator-reported BKX UI success from machine-verified evidence.

## Validation

`go test -count=1 ./cmd/skybind-r1-gateway ./internal/brokerruntime ./internal/brokerissue ./internal/brokergrant ./internal/brokeridentity ./internal/brokeripc`, `go test -race` of the same packages, Android arm64 cross-build of the gateway. Live Android execution must be performed by the operator after hosted CI verifies the new source.

## Rebase correction

The earlier acceptance ZIP was incorrectly pinned to `5f3aa97` and would reject this source. The uploaded source pin and both touched-file preimages have been reverified. Additionally, this rebased artifact preserves the existing `diagnostics` operator command (the previous artifact accidentally displaced it). Source and tests are never silently overridden.
