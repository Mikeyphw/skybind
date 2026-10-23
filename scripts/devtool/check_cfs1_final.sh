#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
python3 -m unittest discover -s tests/seal -p 'test_cfs1*.py' -v
python3 -m unittest discover -s tests/qualification -p 'test_personal_policy.py' -v
python3 -B - <<'PYV'
import json,subprocess,sys
cmd=[sys.executable,'scripts/dev/seal/sb_cfs1.py']
a=subprocess.run(cmd,text=True,capture_output=True)
b=subprocess.run(cmd,text=True,capture_output=True)
assert a.returncode==b.returncode in (0,3)
x=json.loads(a.stdout);y=json.loads(b.stdout)
assert x==y and x['policy']=='SKYBIND_PERSONAL_V1'
assert x['status'] in ('PERSONAL_RELEASE_PENDING','PERSONAL_RELEASE_APPROVED')
assert x['external_signature_required'] is False
print('PERSONAL_RELEASE_CANONICAL_VALIDATION_PASS')
PYV
