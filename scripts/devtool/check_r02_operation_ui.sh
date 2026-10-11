#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
echo '[SB-R02] Native mutation journal, Android namespace selection, cache proofs and job truth'
for mask in 022 077; do
 (umask "$mask"; go test -count=1 ./internal/control ./internal/journal ./internal/daemon ./internal/jobs ./internal/namespace ./internal/mounts/cache ./internal/webui)
done
go test -count=1 ./...
bash scripts/devtool/check_go_race.sh ./internal/control ./internal/journal ./internal/daemon ./internal/jobs
go vet ./...
GOOS=android GOARCH=arm64 CGO_ENABLED=0 go build -buildvcs=false -o /dev/null ./cmd/skybind
node tests/integration/test_r02_webui_flow.mjs
node --check module/webroot/app.js
node --check module/webroot/bridge.js
node --check module/webroot/flow.js
python3 -m unittest discover -s tests/integration -p 'test_*.py' -v
python3 scripts/devtool/check_bootstrap.py release
# The actual release auditor must remain BLOCKED with no fabricated seal.
state='';rc=0
state="$(python3 scripts/dev/release-audit/skybind_audit.py)" || rc=$?
if [ "$rc" -ne 3 ];then echo 'SB-R02: release auditor unexpectedly passed or crashed' >&2;exit 1;fi
printf '%s\n' "$state" | python3 -c 'import json,sys;x=json.load(sys.stdin);assert x["status"]=="BLOCKED" and x["final_seal"]=="NOT_ISSUED" and len(x["milestone_gates"])==8'
echo 'SB-R02_SOURCE_PASS; G01–G08 BLOCKED; final seal NOT_ISSUED'
