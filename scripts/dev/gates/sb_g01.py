#!/usr/bin/env python3
"""G01 personal provider evidence, no external certification requirement."""
from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts/dev/qualification'))
import personal_policy as personal

def evaluate(evidence=None,root=ROOT):
    r=personal.assess(root)
    row=r['gate_checks']['SB-G01']
    return {'gate':'SB-G01','policy':'SKYBIND_PERSONAL_V1',**row,
            'reasons':[x for x in r['reasons'] if 'Q16' in x or 'SOURCE' in x or 'GIT' in x],
            'personal_release_status':r['status'],'external_attestation_required':False}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');ap.add_argument('--repository',type=Path,default=ROOT)
    a=ap.parse_args();r=evaluate(root=a.repository);print(json.dumps(r,sort_keys=True,indent=2))
    return 0 if r['status']=='PERSONAL_EVIDENCE_PASS' else 3
if __name__=='__main__':raise SystemExit(main())
