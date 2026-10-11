#!/usr/bin/env python3
"""Devtool check for a single gate. BLOCKED is the expected honest state now."""
import json
from pathlib import Path
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[2]
if len(sys.argv)!=2 or sys.argv[1] not in [f'SB-G{i:02d}' for i in range(3,9)]:
    sys.exit('usage: check_cg1_gate_state.py SB-G03|...|SB-G08')
gate=sys.argv[1]
p=subprocess.run([sys.executable, 'scripts/dev/gates/sb_cg1.py', '--gate', gate], cwd=ROOT, capture_output=True, text=True, check=False,timeout=60)
if p.returncode!=3:
    sys.exit(f'{gate}: unexpected positive or crashing gate evaluation: {p.returncode}, {p.stderr}')
data=json.loads(p.stdout)
assert data['status']=='BLOCKED' and data['gate']==gate and data['final_seal']=='NOT_ISSUED' and data['reasons'],data
print(f'{gate}: definition checked; actual qualification BLOCKED; reasons={", ".join(data["reasons"])}')
