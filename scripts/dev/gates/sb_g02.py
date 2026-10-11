#!/usr/bin/env python3
"""SB-G02 control-plane milestone evaluator. Source proof, never device seal.

The *definition tests* are deliberately a different workflow from evaluating
real Devtool evidence. Neither installing this gate nor testing its BLOCKED
behavior is equivalent to attaining SOURCE_CONTROL_PASS.
"""
from __future__ import annotations
import argparse, hashlib, json, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
SOURCES = (
 'docs/contracts/typed-operations.json',
 'internal/control/operations.json',
 'internal/control/control.go',
 'internal/control/catalog.go',
 'internal/daemon/wiring.go',
 'internal/mounts/config/config.go',
 'internal/previewproof/proof.go',
 'internal/journal/journal.go',
 'cmd/skybind/main.go',
)
REQUIRED_NEGATIVE = {'unknown_operation','wrong_class','unimplemented_operation',
 'unknown_json_field','proof_replay','stale_revision','atomic_interruption',
 'cli_daemon_equivalence','long_socket_path','private_permissions'}
REQUIRED_OVERLAYS = {'SB-O01','SB-O02','SB-O03','SB-O04','SB-O05','SB-O06','SB-O07','SB-O08','SB-O09'}

def digest(p: Path) -> str:
 return hashlib.sha256(p.read_bytes()).hexdigest()

def evaluate(root: Path = ROOT, *, g01_result: dict | None = None, evidence: Path | None = None) -> dict:
 reasons=[]
 if g01_result is None:
  try:
   import sb_g01
   g01_result=sb_g01.evaluate(root=root)
  except Exception as exc:
   reasons.append('G01 evaluator unavailable: '+type(exc).__name__)
   g01_result={'status':'BLOCKED'}
 if g01_result.get('status')!='SOURCE_BUILD_PASS':
  reasons.append('SB-G01 is not source-qualified')
 sources={}
 for path in SOURCES:
  location=root/path
  if not location.is_file():reasons.append('missing source '+path)
  else:sources[path]=digest(location)
 if sources.get(SOURCES[0])!=sources.get(SOURCES[1]):
  reasons.append('embedded 57-operation catalog drift')
 proof=evidence or root/'build/evidence/sb_g02_source.json'
 if not proof.is_file():reasons.append('missing independent Devtool validation receipts')
 else:
  try:
   record=json.loads(proof.read_text())
   if record.get('schema_version')!=1 or record.get('gate')!='SB-G02':reasons.append('invalid evidence schema')
   if record.get('source_hashes')!=sources:reasons.append('source hash drift')
   if set(record.get('overlay_ids',[]))!=REQUIRED_OVERLAYS:reasons.append('incomplete overlay closure')
   if record.get('warning_count')!=0:reasons.append('warnings not cleared')
   if record.get('device_qualified') is not False or record.get('final_seal') is not False:reasons.append('source gate claimed device or final seal')
   receipts=record.get('fresh_devtool_runs',[])
   if len(receipts)!=2 or len({r.get('run_id') for r in receipts if isinstance(r,dict)})!=2:
    reasons.append('two independent Devtool runs required')
   else:
    for receipt in receipts:
     if receipt.get('source_commit')!=record.get('source_commit') or receipt.get('source_hashes')!=sources or receipt.get('status')!='passed' or receipt.get('warnings')!=0:
      reasons.append('missing fresh-process fixed-point evidence')
     if not REQUIRED_NEGATIVE.issubset(set(receipt.get('negative_tests_passed',[]))):
      reasons.append('negative security matrix incomplete')
     if not receipt.get('evidence_path') or not Path(receipt['evidence_path']).is_dir():
      reasons.append('Devtool run evidence directory missing')
   actual_commit=subprocess.run(['git','-C',str(root),'rev-parse','HEAD'],capture_output=True,text=True,check=False)
   if actual_commit.returncode or record.get('source_commit')!=actual_commit.stdout.strip():
    reasons.append('evaluated source commit not pinned')
  except (OSError,TypeError,ValueError,KeyError) as exc:
   reasons.append('invalid gate evidence: '+type(exc).__name__)
 status='SOURCE_CONTROL_PASS' if not reasons else 'BLOCKED'
 return {'gate':'SB-G02','status':status,'assurance':'SOURCE_ONLY' if not reasons else 'NOT_ATTESTED',
  'reasons':sorted(set(reasons)),'android_device':'NOT_ATTESTED','final_seal':'NOT_ISSUED',
  'source_count':len(sources)}

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');parser.parse_args()
 result=evaluate();print(json.dumps(result,sort_keys=True,indent=2))
 return 0 if result['status']=='SOURCE_CONTROL_PASS' else 3
if __name__=='__main__':raise SystemExit(main())
