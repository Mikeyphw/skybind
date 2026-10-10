#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
echo '[SB-C04] doctor, support and both typed WebUI transports — source validation'
python3 -m unittest discover -s tests/diagnostics -p 'test_*.py' -v
for mask in 022 077; do
 ( umask "$mask"; go test -count=1 ./internal/diagnostics ./internal/doctor ./internal/support ./internal/webui ./internal/daemon ./cmd/skybind )
done
bash scripts/devtool/check_go_race.sh ./internal/diagnostics ./internal/doctor ./internal/support ./internal/webui ./internal/daemon
# Existing suites cannot be hidden by targeted green tests.
go test -count=1 ./...
go vet ./...
GOOS=android GOARCH=arm64 CGO_ENABLED=0 go build -o /dev/null ./cmd/skybind
python3 scripts/devtool/check_bootstrap.py release
python3 - <<'PY'
import json
p=json.load(open('docs/roadmap/SKYBIND_DEVTOOL_OVERLAY_INDEX.json'))
assert [x['status'] for x in p['artifact_sequence'][:4]]==['SOURCE_IMPLEMENTED_NOT_PROMOTED']*4
assert all(x['status']=='SOURCE_IMPLEMENTED_NOT_PROMOTED' for x in p['artifact_sequence'][4:6])
assert all(x['status']=='PLANNED' for x in p['artifact_sequence'][6:])
assert p['starting_position']['gate_qualification']=={'SB-G01':'BLOCKED','SB-G02':'BLOCKED'}
print('SB-C04 source validated; WebUI visual parity C05, device evidence and all release seals remain unqualified')
PY
