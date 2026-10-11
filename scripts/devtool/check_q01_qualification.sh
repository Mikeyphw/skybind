#!/usr/bin/env bash
# Source-only validator; blocked actual gates are expected without external proof.
set -euo pipefail
cd "$(dirname "$0")/../.."
python3 -m unittest discover -s tests/qualification -p 'test_q01_*.py' -v
python3 -m py_compile scripts/dev/qualification/skybind_qualify.py
python3 - <<'PY'
import json,os,pathlib,subprocess,sys
root=pathlib.Path.cwd()
watch=[root/'scripts/dev/runtime/source.lock.json',root/'scripts/dev/gates/sb_g01.py',root/'scripts/dev/seal/sb_cfs1.py']
before=[p.read_bytes() for p in watch]
env={**os.environ,**{key:'' for key in ('SKYBIND_VERIFIED_GATE_EVIDENCE_DIR','SKYBIND_GATE_TRUST_PUBKEY','SKYBIND_GATE_TRUST_KEY_SHA256','SKYBIND_FINAL_SEAL_EVIDENCE_DIR','SKYBIND_FINAL_SEAL_PUBKEY','SKYBIND_FINAL_SEAL_PUBKEY_SHA256')}}
p=subprocess.run([sys.executable,'scripts/dev/qualification/skybind_qualify.py','status'],capture_output=True,text=True,env=env,timeout=40)
assert p.returncode==0,(p.returncode,p.stderr)
r=json.loads(p.stdout)
assert r['qualification']=='RAW_UNATTESTED' and r['final_seal']=='NOT_ISSUED'
assert len(r['gate_statuses'])==8 and all(s=='BLOCKED' for s in r['gate_statuses'].values())
assert before==[p.read_bytes() for p in watch],'unexpected gate/lock mutation'
print('SB-Q01 readiness evaluator and 8 canonical BLOCKED gates: validation PASS (NO QUALIFICATION)')
PY
