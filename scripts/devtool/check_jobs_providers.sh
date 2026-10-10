#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
echo '[SB-C03] jobs, provider and telemetry target checks (source only)'
python3 -m unittest discover -s tests/jobs -p 'test_*.py' -v
for mask in 022 077; do
  ( umask "$mask"; go test -count=1 ./internal/jobs ./internal/provider ./internal/rc ./internal/daemon ./internal/mounts/lifecycle ./cmd/skybind )
done
bash scripts/devtool/check_go_race.sh ./internal/jobs ./internal/provider ./internal/rc ./internal/daemon
# Regenerate no binary artifacts in the Git worktree.
go test -count=1 ./...
go vet ./...
GOOS=android GOARCH=arm64 CGO_ENABLED=0 go build -o /dev/null ./cmd/skybind
python3 scripts/devtool/check_bootstrap.py release
python3 - <<'PY'
import json
p=json.load(open('docs/roadmap/SKYBIND_DEVTOOL_OVERLAY_INDEX.json'))
assert p['artifact_sequence'][2]['status']=='SOURCE_IMPLEMENTED_NOT_PROMOTED'
assert p['artifact_sequence'][3]['status']=='PLANNED'
assert p['artifact_sequence'][-1]['status']=='PLANNED'
print('SB-C03 source tests passed; no Android/RC cloud device evidence, no milestone promotion, no final seal')
PY
