#!/usr/bin/env bash
# SB-CG1: source validation of independent gates, no promotion/seal.
set -euo pipefail
cd "$(dirname "$0")/../.."
# Revalidate impacted whole-product source and negative/fault suites automatically.
python3 -m unittest discover -s tests/gates -p 'test_cg1*.py' -v
python3 -m unittest discover -s tests/integration -p 'test_*.py' -v
python3 -m unittest discover -s tests/diagnostics -p 'test_*.py' -v
python3 -m unittest discover -s tests/webui -p 'test_port.py' -v
python3 -m unittest discover -s tests/seal -p 'test_*.py' -v
python3 scripts/devtool/check_bootstrap.py release
python3 - <<'PY'
import hashlib,json,pathlib,subprocess,sys
root=pathlib.Path.cwd()
tracked=lambda: {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'internal').rglob('*.go')}
before=tracked()
for gate_num in range(3,9):
 p=subprocess.run([sys.executable,'scripts/devtool/check_cg1_gate_state.py',f'SB-G{gate_num:02d}'],capture_output=True,text=True)
 if p.returncode: print(p.stdout,p.stderr,file=sys.stderr);raise SystemExit(p.returncode)
 print(p.stdout.strip())
a=subprocess.run([sys.executable,'scripts/dev/gates/sb_cg1.py'],capture_output=True,text=True)
b=subprocess.run([sys.executable,'scripts/dev/gates/sb_cg1.py'],capture_output=True,text=True)
assert a.returncode==b.returncode==3,(a.returncode,b.returncode,a.stderr,b.stderr)
assert json.loads(a.stdout)==json.loads(b.stdout),'fresh process fixed-point mismatch'
obj=json.loads(a.stdout)
assert obj['status']=='BLOCKED' and obj['final_seal']=='NOT_ISSUED'
assert set(obj['gates'])=={f'SB-G{i:02d}' for i in range(3,9)}
assert set(x['status'] for x in obj['gates'].values())=={'BLOCKED'}
assert obj['dependency_gates']=={'SB-G01':'BLOCKED','SB-G02':'BLOCKED'}
assert before==tracked(),'gate evaluation modified product source'
print('SB-CG1: 6 independent gate evaluators deterministic, read-only, all BLOCKED pending trusted evidence')
PY
