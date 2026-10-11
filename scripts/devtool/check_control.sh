#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
for mask in 022 077; do
  (umask "$mask"; go test -count=1 ./internal/protocol ./internal/control ./internal/daemon ./internal/previewproof ./internal/journal)
done
go vet ./internal/protocol ./internal/control ./internal/daemon ./internal/previewproof ./internal/journal
GOOS=android GOARCH=arm64 CGO_ENABLED=0 go build ./internal/protocol ./internal/control ./internal/daemon ./internal/previewproof ./internal/journal
