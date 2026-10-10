#!/usr/bin/env bash
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export GOTOOLCHAIN=local GOWORK=off GOPROXY=off GOSUMDB=off CGO_ENABLED=0
python3 -m unittest discover -s tests/package -p 'test_*.py' -v
(umask 077; python3 -m unittest discover -s tests/package -p 'test_*.py' -v)
go test -count=1 ./internal/integrity ./internal/runtimeauth ./internal/paths ./internal/atomicfile
GOOS=linux GOARCH=arm64 go build -o /dev/null ./cmd/skybind
GOOS=android GOARCH=arm64 go build -o /dev/null ./cmd/skybind
printf 'SOURCE_TARGETED_PASS only; pinned real upstream provider build not asserted\n'
