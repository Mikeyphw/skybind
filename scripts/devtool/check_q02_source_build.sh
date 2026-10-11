#!/usr/bin/env bash
# Executed BY DEVTOOL overlay validation and the source CI job.
# No live provider acquisition, release claims or separate operator tests.
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python3 -m unittest discover -s tests/qualification -p 'test_q02_*.py' -v
python3 -m py_compile scripts/dev/runtime/source_build.py scripts/dev/runtime/skybind_runtime.py
python3 - <<'PY'
import json,pathlib,subprocess,sys
root=pathlib.Path.cwd();lock=root/'scripts/dev/runtime/source.lock.json'
before=lock.read_bytes()
cmd=[sys.executable,'scripts/dev/runtime/source_build.py','pins']
p=subprocess.run(cmd,capture_output=True,text=True,timeout=30)
assert p.returncode==3 and 'BLOCKED' in p.stderr, (p.returncode,p.stdout,p.stderr)
assert lock.read_bytes()==before,'source lock was mutated'
assert not (root/'build/evidence/sb_g01_provider_builds.json').is_file(), 'unexpected evidence source'
print('SB-Q02: missing external pins => fail-closed; G01 BLOCKED, final seal NOT_ISSUED')
PY
