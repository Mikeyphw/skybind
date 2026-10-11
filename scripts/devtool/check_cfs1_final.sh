#!/usr/bin/env bash
# SB-CFS1: Devtool automatic validator of seal evaluator, not real qualification.
set -euo pipefail
cd "$(dirname "$0")/../.."
python3 -m unittest discover -s tests/seal -p 'test_cfs1*.py' -v
python3 -m unittest discover -s tests/gates -p 'test_cg1*.py' -v
python3 -m unittest discover -s tests/integration -p 'test_campaign_integration.py' -v
python3 -m unittest discover -s tests/diagnostics -p 'test_c04_contract.py' -v
python3 -m unittest discover -s tests/webui -p 'test_port.py' -v
python3 -m unittest discover -s tests -p 'test_bootstrap.py' -v
python3 scripts/devtool/check_bootstrap.py release
python3 - <<'PY'
import hashlib,json,os,pathlib,subprocess,sys
r=pathlib.Path.cwd()
watch=[r/'internal/control/control.go',r/'internal/daemon/wiring.go',r/'module/webroot/style.css']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
before=[sha(p) for p in watch]
env={**os.environ,'SKYBIND_FINAL_SEAL_EVIDENCE_DIR':'','SKYBIND_FINAL_SEAL_PUBKEY':'','SKYBIND_FINAL_SEAL_PUBKEY_SHA256':''}
p=subprocess.run([sys.executable,'scripts/dev/seal/sb_cfs1.py'],capture_output=True,text=True,env=env,check=False,timeout=40)
q=subprocess.run([sys.executable,'scripts/dev/seal/sb_cfs1.py'],capture_output=True,text=True,env=env,check=False,timeout=40)
assert p.returncode==q.returncode==3,(p.returncode,q.returncode,p.stderr,q.stderr)
assert json.loads(p.stdout)==json.loads(q.stdout),'final fixed-point mismatch'
data=json.loads(p.stdout)
assert data['status']=='BLOCKED' and data['final_seal']=='NOT_ISSUED'
assert set(data['milestone_gates'])=={f'SB-G{i:02d}' for i in range(1,9)}
assert all(x=='BLOCKED' for x in data['milestone_gates'].values())
assert data['final_attestation_sha256'] is None
assert before==[sha(p) for p in watch],'final checker wrote product sources'
print('SB-CFS1: verifier definition PASS; 8 external milestone gates BLOCKED; release seal NOT ISSUED')
PY
