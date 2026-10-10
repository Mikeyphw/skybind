#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
echo '[SB-FP02] CLI, crypt provenance, local-path jobs: targeted Devtool validation'
for mask in 022 077; do
  (umask "$mask"; go test -count=1 ./cmd/skybind ./internal/provider ./internal/jobs ./internal/daemon)
done
node tests/integration/test_fp02_crypto_parity.mjs
node tests/integration/test_fp01_webui_parity.mjs
for script in module/webroot/bridge.js module/webroot/parity.js; do node --check "$script"; done
go test -count=1 ./...
bash scripts/devtool/check_go_race.sh ./cmd/skybind ./internal/jobs ./internal/provider
go vet ./...
GOOS=android GOARCH=arm64 CGO_ENABLED=0 go build -buildvcs=false -o /dev/null ./cmd/skybind
python3 -m unittest discover -s tests/integration -p 'test_*.py' -v
python3 scripts/devtool/check_bootstrap.py release
result='';rc=0
result="$(python3 scripts/dev/release-audit/skybind_audit.py)" || rc=$?
if [ "$rc" -ne 3 ]; then echo 'SB-FP02: unexpected release qualification' >&2; exit 1; fi
printf '%s\n' "$result" | python3 -c 'import json,sys; x=json.load(sys.stdin); assert x["status"]=="BLOCKED" and x["final_seal"]=="NOT_ISSUED"'
echo 'SB-FP02_SOURCE_PASS; device/cloud not attested; G01-G08 BLOCKED; final seal NOT_ISSUED'
