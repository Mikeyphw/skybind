#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
for mask in 022 077; do
 (umask "$mask"; go test -count=1 ./internal/mounts/config ./internal/previewproof)
done
go vet ./internal/mounts/config
GOOS=android GOARCH=arm64 CGO_ENABLED=0 go build ./internal/mounts/config
