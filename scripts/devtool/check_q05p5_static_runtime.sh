#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib,tomllib
root=pathlib.Path.cwd()
config=tomllib.loads((root/'.devtool.toml').read_text())
assert config['targets']['skybind']['workflows']['q05p5-static-runtime-integrity']==['job:q05p5-static-runtime-integrity']
policy=json.loads((root/'scripts/dev/runtime/source.selection.json').read_text())
assert policy['gate_g01']=='BLOCKED' and policy['final_seal']=='NOT_ISSUED'
source=(root/'internal/integrity/integrity.go').read_text()
assert 'len(m.Files) < 2 || len(m.Files) > 66' in source
assert 'len(m.Files) < 3 || len(m.Files) > 66' not in source
PY
GOTOOLCHAIN=local go test -count=1 ./internal/integrity ./internal/runtimeauth
printf '%s\n' 'SB-Q05P5 SOURCE_ONLY_PASS: both static runtime files authenticated in fixture; Android device retest REQUIRED; G01-G08 BLOCKED; seal NOT_ISSUED'
