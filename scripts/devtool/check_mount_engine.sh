#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
echo '[SB-C01] frozen 8-delivery roadmap, 45-obligation legacy ledger, 57 typed operations'
python3 -m unittest discover -s tests -p 'test_bootstrap.py' -v
python3 -m unittest discover -s tests/contracts -p 'test_*.py' -v
python3 -m unittest discover -s tests/cli -p 'test_*.py' -v
echo '[SB-C01] positive/negative mount ownership, supervisor, resource policy, cache and daemon wiring'
for mask in 022 077; do
 (umask "$mask"; go test -count=1 ./internal/mounts/... ./internal/daemon ./internal/control ./cmd/skybind)
done
echo '[SB-C01] full regression, portability and toolchain checks'
go test -count=1 ./...
# Race detector is evidence only on supported hosts, and absence isn't PASS.
bash scripts/devtool/check_go_race.sh ./internal/mounts/... ./internal/daemon ./internal/control
go vet ./...
GOOS=android GOARCH=arm64 CGO_ENABLED=0 go build -o /dev/null ./cmd/skybind
python3 - <<'PY'
import json,tomllib
with open('.devtool.toml','rb') as f: cfg=tomllib.load(f)
assert cfg['targets']['skybind']['workflows']['mount-source']==['job:mount-source-validation']
i=json.load(open('docs/roadmap/SKYBIND_DEVTOOL_OVERLAY_INDEX.json'))
assert i['coverage_map']['SB-O10']=='SB-C01'
assert i['coverage_map']['SB-O14']=='SB-C01'
assert all(x!='PASS' for x in i['starting_position']['gate_qualification'].values())
print('SB-C01 SOURCE_ONLY; G01/G02 BLOCKED; Android mount/device gate NOT_ATTESTED')
PY
