#!/usr/bin/env python3
"""Canonical Skybind PERSONAL release decision; no external seal or signing."""
from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts/dev/qualification'))
import personal_policy as personal
GATES=personal.GATES
def evaluate(root=ROOT):
    doc=personal.assess(root)
    return {'schema_version':1,'policy':'SKYBIND_PERSONAL_V1',
            'status':doc['status'],'milestone_gates':{k:v['status'] for k,v in doc['gate_checks'].items()},
            'source_commit':doc['source_commit'],'candidate':doc['candidate'],
            'personal_scope_only':True,'owner_approval':doc['owner_approval'],
            'final_seal':'PERSONAL_OWNER_APPROVED' if doc['owner_approval'] else 'PENDING_OWNER_APPROVAL',
            'reasons':doc['reasons'],'external_signature_required':False,
            'unverified_hardware_compatibility_not_claimed':True}
def main():
    p=argparse.ArgumentParser();p.add_argument('--repository',type=Path,default=ROOT)
    o=p.parse_args();r=evaluate(o.repository);print(json.dumps(r,sort_keys=True,indent=2))
    return 0 if r['status']=='PERSONAL_RELEASE_APPROVED' else 3
if __name__=='__main__':raise SystemExit(main())
