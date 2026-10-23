#!/usr/bin/env python3
"""Check personal gate schema and explicitly pending/approved state."""
import json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if len(sys.argv)!=2 or sys.argv[1] not in [f'SB-G{i:02d}' for i in range(3,9)]:
    sys.exit('usage: check_cg1_gate_state.py SB-G03..SB-G08')
gate=sys.argv[1]
p=subprocess.run([sys.executable,str(ROOT/'scripts/dev/gates/sb_cg1.py'),'--gate',gate],
                 cwd=ROOT,capture_output=True,text=True,timeout=50)
assert p.returncode in (0,3),(p.returncode,p.stderr)
d=json.loads(p.stdout)
assert d['gate']==gate and d['status'] in ('PENDING_PERSONAL_CHECK','PERSONAL_EVIDENCE_PASS','PERSONAL_OWNER_ACCEPTED')
print(f"{gate}: {d['status']} (personal scope; no external signature requirement)")
