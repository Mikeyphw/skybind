#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
echo '[SB-C02] bounded namespace scans, protected groups, proofs, compensation, ownership recovery'
python3 -m unittest discover -s tests/platform -p 'test_*.py' -v
for mask in 022 077; do
  ( umask "$mask"; go test -count=1 ./internal/namespace ./internal/rootmgr ./internal/platformlifecycle ./internal/daemon ./internal/mounts/lifecycle ./cmd/skybind )
done
for script in module/action.sh module/customize.sh module/post-fs-data.sh module/service.sh module/uninstall.sh; do
  /bin/sh -n "$script"
done
echo '[SB-C02] affected and whole-source regressions'
go test -count=1 ./...
bash scripts/devtool/check_go_race.sh ./internal/namespace ./internal/daemon ./internal/mounts/lifecycle
go vet ./...
GOOS=android GOARCH=arm64 CGO_ENABLED=0 go build -o /dev/null ./cmd/skybind
python3 - <<'PY'
import json,tomllib
with open('.devtool.toml','rb') as f:c=tomllib.load(f)
assert c['targets']['skybind']['workflows']['android-platform']==['job:android-platform-source']
i=json.load(open('docs/roadmap/SKYBIND_DEVTOOL_OVERLAY_INDEX.json'))
assert all(i['coverage_map'][f'SB-O{x}']=='SB-C02' for x in range(15,20))
assert i['artifact_sequence'][1]['status']=='SOURCE_IMPLEMENTED_NOT_PROMOTED'
assert i['artifact_sequence'][-1]['status']=='PLANNED'
assert i['starting_position']['gate_qualification']=={'SB-G01':'BLOCKED','SB-G02':'BLOCKED'}
print('SB-C02 SOURCE ONLY; device/app visibility not certified; gates not promoted; final seal not issued')
PY
