#!/usr/bin/env bash
# SB-R01: implementation validation only; no external upstream/device/seal claim.
set -euo pipefail
cd "$(dirname "$0")/../.."
echo '[SB-R01] Runtime authority + mounted configuration lifecycle integration'
python3 -m unittest discover -s tests/fault -p 'test_*.py' -v
python3 -m unittest discover -s tests/integration -p 'test_*.py' -v
for mask in 022 077;do
  (umask "$mask"; go test -count=1 ./internal/mounts/config ./internal/mounts/lifecycle ./internal/daemon ./internal/runtimeauth)
done
go test -count=1 ./...
bash scripts/devtool/check_go_race.sh ./internal/mounts/config ./internal/mounts/lifecycle ./internal/daemon
go vet ./...
GOOS=android GOARCH=arm64 CGO_ENABLED=0 go build -buildvcs=false -o /dev/null ./cmd/skybind
python3 scripts/devtool/check_bootstrap.py release
# All real gates remain BLOCKED; source patch must not promote them.
state='';rc=0
state="$(python3 scripts/dev/release-audit/skybind_audit.py)" || rc=$?
if [ "$rc" -ne 3 ];then echo 'SB-R01: release audit improperly passed or crashed' >&2;exit 1;fi
printf '%s\n' "$state" | python3 -c 'import json,sys;x=json.load(sys.stdin);assert x["status"]=="BLOCKED" and x["final_seal"]=="NOT_ISSUED" and len(x["milestone_gates"])==8'
echo 'SB-R01_SOURCE_PASS; G01-G08 BLOCKED; no release seal or device qualification'
