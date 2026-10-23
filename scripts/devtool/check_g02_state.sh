#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
# Personal policy must never claim passed negative tests when none configured.
python3 -B - <<'PYV'
import json,subprocess,sys
p=subprocess.run([sys.executable,'scripts/dev/gates/sb_g02.py','--check'],capture_output=True,text=True)
assert p.returncode in (0,3),(p.returncode,p.stderr)
d=json.loads(p.stdout)
assert d['policy']=='SKYBIND_PERSONAL_V1' and d['gate']=='SB-G02'
assert d['external_attestation_required'] is False
assert d['status'] in ('PERSONAL_EVIDENCE_PASS','PENDING_PERSONAL_CHECK')
print(json.dumps(d,sort_keys=True))
PYV
