#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
python3 -m unittest discover -s tests/cli -p 'test_*.py' -v
python3 -m unittest discover -s tests/contracts -p 'test_*.py' -v
for mask in 022 077; do
  (umask "$mask"; go test -count=1 ./internal/control ./internal/daemon ./internal/protocol ./internal/mounts/config ./cmd/skybind)
done
bash scripts/devtool/check_go_race.sh ./internal/control ./internal/daemon ./internal/mounts/config ./cmd/skybind
go vet ./...
GOOS=android GOARCH=arm64 CGO_ENABLED=0 go build -o /dev/null ./cmd/skybind
