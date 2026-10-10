#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
echo '[SB-FP03] platform parity: source-validated, device evidence still blocked'
for mask in 022 077; do
 ( umask "$mask"; go test -count=1 ./internal/mounts/policy ./internal/namespace ./internal/doctor ./internal/daemon ./internal/jobs ./cmd/skybind )
done
go test -count=1 ./...
bash scripts/devtool/check_go_race.sh ./internal/mounts/policy ./internal/namespace ./internal/doctor ./internal/daemon ./internal/jobs
go vet ./...
GOOS=android GOARCH=arm64 CGO_ENABLED=0 go build -buildvcs=false -o /dev/null ./cmd/skybind
python3 scripts/devtool/check_bootstrap.py release
node tests/integration/test_fp02_crypto_parity.mjs
node tests/integration/test_fp01_webui_parity.mjs
res=''; rc=0
res="$(python3 scripts/dev/release-audit/skybind_audit.py)" || rc=$?
if [[ "$rc" != 3 ]]; then echo 'Unexpected release qualification' >&2; exit 1; fi
printf '%s\n' "$res" | python3 -c 'import sys,json;x=json.load(sys.stdin);assert x["status"]=="BLOCKED" and x["final_seal"]=="NOT_ISSUED"'
echo 'SB-FP03 source PASS; metering may remain UNKNOWN on unsupported Android dumpsys versions; G01-G08 BLOCKED; final seal NOT_ISSUED'
