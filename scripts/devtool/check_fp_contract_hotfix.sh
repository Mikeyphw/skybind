#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
echo '[SB-FPH01] source-level repair promises and typed CLI/Doctor contract'
for mask in 022 077; do
 ( umask "$mask"; go test -count=1 ./cmd/skybind ./internal/doctor ./internal/daemon ./internal/mounts/policy ./internal/jobs ./internal/provider ./internal/mounts/lifecycle )
done
node tests/integration/test_fp_hotfix_contract.mjs
node tests/integration/test_fp01_webui_parity.mjs
node tests/integration/test_fp02_crypto_parity.mjs
go test -count=1 ./...
bash scripts/devtool/check_go_race.sh ./cmd/skybind ./internal/doctor ./internal/daemon ./internal/mounts/lifecycle
go vet ./...
GOOS=android GOARCH=arm64 CGO_ENABLED=0 go build -buildvcs=false -o /dev/null ./cmd/skybind
python3 scripts/devtool/check_bootstrap.py release
result=''; rc=0
result="$(python3 scripts/dev/release-audit/skybind_audit.py)" || rc=$?
if [[ "$rc" -ne 3 ]]; then echo 'Unexpected qualified release status' >&2; exit 1; fi
printf '%s\n' "$result" | python3 -c 'import json,sys;x=json.load(sys.stdin);assert x["status"]=="BLOCKED" and x["final_seal"]=="NOT_ISSUED"'
echo 'SB-FPH01 contracts validated; physical-device/G01-G08 remain unqualified'
