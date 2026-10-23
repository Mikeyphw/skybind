#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
python3 -m unittest discover -s tests/gates -p 'test_cg1*.py' -v
python3 -m unittest discover -s tests/qualification -p 'test_personal_policy.py' -v
for n in 03 04 05 06 07 08; do python3 scripts/devtool/check_cg1_gate_state.py SB-G$n; done
python3 -B - <<'PYV'
import json,subprocess,sys
cmd=[sys.executable,'scripts/dev/gates/sb_cg1.py']
a=subprocess.run(cmd,capture_output=True,text=True)
b=subprocess.run(cmd,capture_output=True,text=True)
assert a.returncode==b.returncode in (0,3)
assert json.loads(a.stdout)==json.loads(b.stdout)
d=json.loads(a.stdout)
assert set(d['gates'])=={f'SB-G{i:02d}' for i in range(3,9)}
assert d['external_attestation_required'] is False
print('PERSONAL_GATES_DETERMINISTIC')
PYV
