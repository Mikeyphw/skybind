#!/usr/bin/env python3
"""C06 personal release source/candidate audit. No external seal workflow."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts/dev/qualification'))
import personal_policy

def evaluate(repo:Path=ROOT)->dict:
    doc=personal_policy.assess(repo)
    return {'schema_version':1,'product':'skybind','overlay':'SB-C06',
            'policy':'SKYBIND_PERSONAL_V1','status':doc['status'],
            'personal_scope_only':True,'owner_approval':doc['owner_approval'],
            'milestone_gates':{k:v['status'] for k,v in doc['gate_checks'].items()},
            'reasons':doc['reasons'],'external_qualification_required':False}

def blocked_report(repo:Path=ROOT)->dict:
    """Historical import alias. Return the *actual* personal status, not a fabricated BLOCKED gate."""
    return evaluate(repo)

def main():
    p=argparse.ArgumentParser();p.add_argument('--repository',type=Path,default=ROOT)
    a=p.parse_args();doc=evaluate(a.repository)
    print(json.dumps(doc,sort_keys=True))
    return 0 if doc['status']=='PERSONAL_RELEASE_APPROVED' else 3
if __name__=='__main__':raise SystemExit(main())
