#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
echo '[SB-FP01] WebUI semantic parity: selected contracts, negative tests, private idle expiry'
for mask in 022 077; do
  (umask "$mask"; go test -count=1 ./internal/runtimeauth ./internal/webui ./internal/uisettings ./cmd/skybind)
done
node tests/integration/test_fp01_webui_parity.mjs
node tests/integration/test_r02_webui_flow.mjs
for filename in module/webroot/app.js module/webroot/bridge.js module/webroot/parity.js; do node --check "$filename"; done
go test -count=1 ./...
bash scripts/devtool/check_go_race.sh ./internal/webui ./internal/runtimeauth ./cmd/skybind
go vet ./...
GOOS=android GOARCH=arm64 CGO_ENABLED=0 go build -buildvcs=false -o /dev/null ./cmd/skybind
python3 -m unittest discover -s tests/integration -p 'test_*.py' -v
python3 scripts/devtool/check_bootstrap.py release
# Evidence gating is not a source test success. Assert gates remain unqualified.
result='';rc=0
result="$(python3 scripts/dev/release-audit/skybind_audit.py)" || rc=$?
if [ "$rc" -ne 3 ];then echo 'SB-FP01: release auditor unexpectedly succeeded or crashed' >&2;exit 1;fi
printf '%s\n' "$result" | python3 -c 'import json,sys;x=json.load(sys.stdin);assert x["status"]=="BLOCKED" and x["final_seal"]=="NOT_ISSUED"'
echo 'SB-FP01_SOURCE_PASS; original CSS/HTML unchanged; browser/device parity NOT_ATTESTED; G01-G08 BLOCKED'
