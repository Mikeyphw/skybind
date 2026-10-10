#!/usr/bin/env bash
set -euo pipefail
export GOTOOLCHAIN=local
export GOWORK=off
export GOPROXY=off
export GOSUMDB=off
export CGO_ENABLED=0
printf '[SB-O03] Go source unit and adversarial tests (umask 022)\n'
( umask 022; go test -count=1 ./internal/paths ./internal/atomicfile ./cmd/skybind )
printf '[SB-O03] Go source unit and adversarial tests (Termux umask 077)\n'
( umask 077; go test -count=1 ./internal/paths ./internal/atomicfile ./cmd/skybind )
printf '[SB-O03] Static linux/arm64 compilation\n'
GOOS=linux GOARCH=arm64 go build -o /dev/null ./cmd/skybind
printf '[SB-O03] Static android/arm64 compilation\n'
GOOS=android GOARCH=arm64 go build -o /dev/null ./cmd/skybind
printf '[SB-O03] All source-only checks passed (not device qualification)\n'
