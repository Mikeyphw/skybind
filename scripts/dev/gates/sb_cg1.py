#!/usr/bin/env python3
"""G03..G08 personal acceptance, preserving per-gate visibility without attestation."""
from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts/dev/qualification'))
import personal_policy as personal
GATES=tuple(f'SB-G{i:02d}' for i in range(3,9))
def evaluate_all(root=ROOT):
    r=personal.assess(root)
    return {'schema_version':1,'policy':'SKYBIND_PERSONAL_V1','status':r['status'],
            'dependency_gates':{g:r['gate_checks'][g]['status'] for g in ('SB-G01','SB-G02')},
            'gates':{g:{'gate':g,**r['gate_checks'][g],
                        'owner_approval':r['owner_approval']} for g in GATES},
            'external_attestation_required':False,'personal_scope_only':True}
def main():
    p=argparse.ArgumentParser();p.add_argument('--repository',type=Path,default=ROOT)
    p.add_argument('--gate',choices=GATES);p.add_argument('--check',action='store_true')
    a=p.parse_args();r=evaluate_all(a.repository)
    out=r['gates'][a.gate] if a.gate else r
    print(json.dumps(out,sort_keys=True,indent=2))
    return 0 if (out['status'] if a.gate else r['status']) in ('PERSONAL_EVIDENCE_PASS','PERSONAL_OWNER_ACCEPTED','PERSONAL_RELEASE_APPROVED') else 3
if __name__=='__main__':raise SystemExit(main())
