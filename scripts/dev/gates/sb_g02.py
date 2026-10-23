#!/usr/bin/env python3
"""G02 owner-controlled Devtool negative-test evidence, no custody signatures."""
from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts/dev/qualification'))
import personal_policy as personal
SOURCES=tuple(('docs/contracts/typed-operations.json','internal/control/operations.json',
               'internal/control/control.go','internal/control/catalog.go','internal/daemon/wiring.go',
               'internal/mounts/config/config.go','internal/previewproof/proof.go',
               'internal/journal/journal.go','cmd/skybind/main.go'))
digest=personal.digest
REQUIRED_NEGATIVE={'unknown_operation','wrong_class','unimplemented_operation',
    'unknown_json_field','proof_replay','stale_revision','atomic_interruption',
    'cli_daemon_equivalence','long_socket_path','private_permissions'}

def evaluate(root=ROOT,*,g01_result=None,evidence=None):
    r=personal.assess(root);row=r['gate_checks']['SB-G02']
    return {'gate':'SB-G02','policy':'SKYBIND_PERSONAL_V1',**row,
            'reasons':[x for x in r['reasons'] if 'Q17' in x or 'SOURCE' in x or 'GIT' in x],
            'personal_release_status':r['status'],'external_attestation_required':False}
def main():
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');p.add_argument('--repository',type=Path,default=ROOT)
    o=p.parse_args();r=evaluate(root=o.repository);print(json.dumps(r,sort_keys=True,indent=2))
    return 0 if r['status']=='PERSONAL_EVIDENCE_PASS' else 3
if __name__=='__main__':raise SystemExit(main())
