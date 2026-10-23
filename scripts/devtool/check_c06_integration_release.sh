#!/usr/bin/env bash
# SB-C06; source and fault validation only. No device or release qualification.
set -euo pipefail
cd "$(dirname "$0")/../.."
echo '[SB-C06] Whole-product source, release candidate & safety fault matrix'
python3 -m unittest discover -s tests/integration -p 'test_*.py' -v
python3 -m unittest discover -s tests/fault -p 'test_*.py' -v
python3 -m unittest discover -s tests/device -p 'test_*.py' -v
python3 -m unittest discover -s tests/seal -p 'test_*.py' -v
python3 -m unittest discover -s tests/security -p 'test_*.py' -v
python3 -m unittest discover -s tests/webui -p 'test_port.py' -v
python3 -m unittest discover -s tests/webui -p 'test_browser.py' -v
python3 -m unittest discover -s tests/contracts -p 'test_*.py' -v
python3 -m unittest discover -s tests/diagnostics -p 'test_*.py' -v
python3 -m unittest discover -s tests/jobs -p 'test_*.py' -v
python3 scripts/devtool/check_bootstrap.py release
if command -v node >/dev/null 2>&1;then
 node --check module/webroot/app.js
 node --check module/webroot/model.js
 node --check module/webroot/bridge.js
 node tests/webui/test_bridge.mjs
else
 echo 'SKYBIND_C06_JS_BROWSER_NOT_ATTESTED: Node not installed'
fi
for mask in 022 077;do
 (umask "$mask"; go test -count=1 ./...)
done
bash scripts/devtool/check_go_race.sh ./internal/daemon ./internal/control ./internal/webui ./internal/jobs ./internal/mounts/lifecycle ./internal/namespace

go vet ./...
GOOS=android GOARCH=arm64 CGO_ENABLED=0 go build -buildvcs=false -o /dev/null ./cmd/skybind
# Personal owner approval is separate from source tests. Expect pending or approved.
state=''
rc=0
state="$(python3 scripts/dev/release-audit/skybind_audit.py)" || rc=$?
if [ "$rc" -ne 3 ] && [ "$rc" -ne 0 ];then echo 'personal release audit crashed' >&2;exit 1;fi
printf '%s\n' "$state" | python3 -c 'import sys,json;p=json.load(sys.stdin);assert p["status"] in ("PERSONAL_RELEASE_PENDING","PERSONAL_RELEASE_APPROVED") and p["policy"]=="SKYBIND_PERSONAL_V1" and len(p["milestone_gates"])==8 and p["external_qualification_required"] is False'
echo 'SKYBIND_C06_SOURCE_PASS; personal release approval evaluated separately'
