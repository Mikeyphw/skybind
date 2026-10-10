#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
echo '[SB-C05] Original WebUI reference fidelity, native typed integration and source safety'
python3 -m unittest discover -s tests/webui -p 'test_port.py' -v
python3 -m unittest discover -s tests/webui -p 'test_browser.py' -v
if command -v node >/dev/null 2>&1; then
 node --check module/webroot/app.js
 node --check module/webroot/model.js
 node --check module/webroot/bridge.js
 node tests/webui/test_bridge.mjs
else
 echo 'SB-C05_JS_ENGINE_NOT_ATTESTED: Node unavailable; static reference and Go tests remain mandatory'
fi
for mask in 022 077; do
 (umask "$mask";go test -count=1 ./internal/uisettings ./internal/webui ./internal/daemon ./cmd/skybind)
done
bash scripts/devtool/check_go_race.sh ./internal/uisettings ./internal/webui ./internal/daemon
go test -count=1 ./...
go vet ./...
GOOS=android GOARCH=arm64 CGO_ENABLED=0 go build -o /dev/null ./cmd/skybind
python3 scripts/devtool/check_bootstrap.py release
python3 - <<'PY'
import json
p=json.load(open('docs/roadmap/SKYBIND_DEVTOOL_OVERLAY_INDEX.json'))
assert [x['status'] for x in p['artifact_sequence'][:5]] == ['SOURCE_IMPLEMENTED_NOT_PROMOTED'] * 5
assert p['artifact_sequence'][5]['status'] in ('PLANNED','SOURCE_IMPLEMENTED_NOT_PROMOTED')
assert all(x['status']=='PLANNED' for x in p['artifact_sequence'][6:])
assert p['starting_position']['gate_qualification']=={'SB-G01':'BLOCKED','SB-G02':'BLOCKED'}
print('SB-C05 SOURCE-ONLY qualification: no Android/WebView visual parity, milestone promotion or release seal')
PY
