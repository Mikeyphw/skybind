#!/usr/bin/env python3
"""SB-Q15: source-bound, fail-closed G01/G02 evidence readiness report.

Never creates G01/G02 evaluator input, independent receipts, private keys, or a seal.
Q14 summary is a lead; exact downloaded bytes and an externally pinned owner
key are rechecked locally before calling its signed claims VERIFIED_OWNER_ONLY.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts/dev/release'))
sys.path.insert(0,str(ROOT/'scripts/dev/gates'))
sys.path.insert(0,str(ROOT/'scripts/dev/seal'))
from q14_private_signing import verify as verify_private, SUBJECT_NAMES, MANIFEST, SIGNATURE, PUBLIC
import q13_reproducibility as q13
import sb_g01, sb_g02
from sb_cfs1 import evaluate as cfs1_evaluate

SHA40=re.compile(r'[0-9a-f]{40}\Z')
SHA64=re.compile(r'[0-9a-f]{64}\Z')
REPO=re.compile(r'[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+\Z')
EXACT_LANE_FILES=set(SUBJECT_NAMES)|{MANIFEST,SIGNATURE,PUBLIC}

def sha(path:Path)->str:
 h=hashlib.sha256()
 with path.open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
 return h.hexdigest()

def checked_json(path:Path,max_bytes:int=2_000_000)->dict:
 if path.is_symlink() or not path.is_file() or path.stat().st_size>max_bytes:
  raise ValueError('MISSING_LINKED_OR_OVERSIZED_INPUT')
 obj=json.loads(path.read_bytes())
 if not isinstance(obj,dict): raise ValueError('NONOBJECT_INPUT')
 return obj

def checked_lane(dir:Path)->None:
 if dir.is_symlink() or not dir.is_dir(): raise ValueError('LANE_DIRECTORY_MISSING_OR_LINKED')
 members={p.name for p in dir.iterdir()}
 if members!=EXACT_LANE_FILES or any(p.is_symlink() or not p.is_file() for p in dir.iterdir()):
  raise ValueError('LANE_FILE_SET_INVALID')

def crosscheck_q14(root:Path, report:dict, artifact_root:Path, trust_key:Path,
                    *, github_identity:bool=False)->dict:
 run=report.get('run',{})
 if (report.get('schema_version')!=1 or report.get('campaign')!='SB-Q14' or
     report.get('final_seal')!='NOT_ISSUED' or report.get('independent_attestation') is not False or
     not isinstance(run,dict)):
  raise ValueError('Q14_REPORT_IDENTITY_INVALID')
 repo=run.get('repository'); commit=run.get('head_sha');rid=run.get('run_id');attempt=run.get('run_attempt')
 if (not isinstance(repo,str) or not REPO.fullmatch(repo) or
     not isinstance(commit,str) or not SHA40.fullmatch(commit) or
     type(rid) is not int or rid<1 or type(attempt) is not int or attempt<1 or
     run.get('workflow')!='skybind-q14-attested-candidates.yml' or
     run.get('conclusion')!='success' or run.get('metadata_source')!='AUTHENTICATED_GITHUB_API'):
  raise ValueError('Q14_RUN_IDENTITY_INVALID')
 if report.get('private_ci_signatures_verified') is not True or report.get('all_four_attested') is not False:
  raise ValueError('Q14_OWNER_SIGNATURE_CLAIM_NOT_VALID')
 if not trust_key.is_file() or trust_key.is_symlink():raise ValueError('PINNED_OWNER_KEY_MISSING')
 root_art=artifact_root.resolve(strict=True)
 trusted=trust_key.resolve(strict=True)
 if trusted.is_relative_to(root_art) or trusted.is_relative_to(root.resolve(strict=True)):
  raise ValueError('KEY_FROM_ARTIFACT_OR_REPOSITORY_FORBIDDEN')
 identity={'repo':repo,'head_sha':commit,'run_id':rid,'attempt':attempt}
 inspected={}; signatures={}
 for label in ('A','B'):
  path=artifact_root/('lane-'+label)
  checked_lane(path)
  signature=verify_private(path, trust_key, lane=label,**identity)
  if signature.get('status')!='PRIVATE_ED25519_SIGNATURE_VERIFIED_NOT_CFS1':
   raise ValueError('OWNER_SIGNATURE_INVALID_'+label)
  detail=q13.inspect_lane(path,root)
  if detail['status']!='VALID_UNQUALIFIED_LANE' or detail.get('build_source',{}).get('commit')!=commit:
   raise ValueError('BUILD_SOURCE_OR_PROVIDER_INVALID_'+label)
  for prov in ('bclone','newfuture'):
   claimed=(report.get('lanes',{}).get(label,{}).get('providers',{}).get(prov,{}))
   origin=(detail['providers'][prov])
   if claimed.get('sha256')!=origin['sha256'] or claimed.get('members')!=origin['members']:
    raise ValueError('Q14_REPORT_VS_ORIGINAL_BYTES_MISMATCH_'+label+'_'+prov)
   statement=report.get('signed_candidate_provenance',{}).get(label,{}).get(prov,{})
   if (statement.get('candidate_sha256')!=origin['sha256'] or
       statement.get('public_key_sha256')!=signature['public_key_sha256'] or
       statement.get('status')!='PRIVATE_ED25519_SIGNATURE_VERIFIED_NOT_CFS1'):
    raise ValueError('Q14_REPORT_VS_SIGNATURE_MISMATCH_'+label+'_'+prov)
  inspected[label]=detail
  signatures[label]={'status':signature['status'],'owner_public_key_sha256':signature['public_key_sha256'],
                     'candidate_evidence_sha256':signature['subjects_sha256']['candidate-evidence.json']}
 parity=q13.same_provider(inspected['A'],inspected['B'])
 if any(x['status']!='BYTE_IDENTICAL_UNATTESTED' for x in parity.values()):
  raise ValueError('CI_PAIR_NOT_REPRODUCIBLE')
 for label in ('A','B'):
  if q13.cross_provider(inspected[label])['status']!='SHARED_PAYLOAD_MATCH_UNATTESTED':
   raise ValueError('CROSS_PROVIDER_HELPER_OR_DAEMON_MISMATCH')
 identity_status='RECORDED_FROM_Q14_NOT_FRESHLY_AUTHENTICATED'
 if github_identity:
  # GitHub authenticated metadata still does not make the maintainer signer independent.
  from q14_attestation import authenticated_run
  observed=authenticated_run(repo,rid)
  for field in ('head_sha','run_attempt','workflow','repository','run_id'):
   if observed.get(field)!=run.get(field):raise ValueError('FRESH_GITHUB_RUN_IDENTITY_DRIFT')
  identity_status='REAUTHENTICATED_GITHUB_API'
 return {'status':'OWNER_SIGNED_CANDIDATES_REVERIFIED_NOT_INDEPENDENT',
         'run_id':rid,'repository':repo,'source_commit':commit,'ci_identity':identity_status,
         'lanes':signatures,'providers':{p:{'candidate_sha256':parity[p]['lane_a_sha256'],
                       'byte_identical':True} for p in ('bclone','newfuture')},
         'independent_build_custody':False,'cfs1_gate_evidence':False}

def gate_contract(root:Path)->dict:
 lock=root/'scripts/dev/runtime/source.lock.json'
 sources={name: sha(root/name) if (root/name).is_file() else None for name in sb_g02.SOURCES}
 r1=sb_g01.evaluate(evidence=root/'build/evidence/sb_g01_provider_builds.json',root=root)
 r2=sb_g02.evaluate(root=root,g01_result=r1)
 return {
  'SB-G01': {'actual':r1['status'],'actual_reasons':r1.get('reasons',[]),
    'authority':'scripts/dev/gates/sb_g01.py',
    'required_input':'build/evidence/sb_g01_provider_builds.json',
    'required_qualification':'REAL_PINNED_PROVIDER_BUILD',
    'source_lock_sha256':sha(lock) if lock.is_file() else None,
    'required_original_overlays':list(sb_g01.REQUIRE),
    'needs':'two independent verified official-source provider build records per provider, byte-verified original archives, lock binding, matching FUSE helper',
    'q14_is_substitute':False},
  'SB-G02': {'actual':r2['status'],'actual_reasons':r2.get('reasons',[]),
    'authority':'scripts/dev/gates/sb_g02.py',
    'required_input':'build/evidence/sb_g02_source.json',
    'required_original_overlays':sorted(sb_g02.REQUIRED_OVERLAYS),
    'required_negative_cases':sorted(sb_g02.REQUIRED_NEGATIVE),
    'required_source_hashes':sources,
    'needs':'two distinct fresh independent Devtool fixed-point runs with raw evidence directories, source hashes, negative tests and zero warnings',
    'q14_is_substitute':False},
 }

def evaluate(root:Path,q14_report:Path,artifact_root:Path,trust_key:Path,*,reauthenticate:bool=False)->dict:
 errors=[];ci={'status':'NOT_VERIFIED'}
 try:
  raw=checked_json(q14_report)
  ci=crosscheck_q14(root,raw,artifact_root,trust_key,github_identity=reauthenticate)
 except (OSError,ValueError,KeyError,TypeError,RuntimeError,subprocess.TimeoutExpired,json.JSONDecodeError) as e:
  errors.append(type(e).__name__+': '+str(e)[:140])
 gates=gate_contract(root)
 seal=cfs1_evaluate(root=root)
 if seal.get('final_seal')!='NOT_ISSUED' or seal.get('status')!='BLOCKED':
  raise ValueError('UNEXPECTED_CFS1_STATE_REQUIRES_INDEPENDENT_REVIEW')
 return {'schema_version':1,'campaign':'SB-Q15','status':'EVIDENCE_PREPARATION_ONLY_NOT_RELEASE_QUALIFIED',
  'owner_signed_ci':ci,'errors':errors,'gate_contracts':gates,
  'cfs1':{'status':seal['status'],'gates':seal['milestone_gates'],
          'reasons':seal['reasons']},
  'independent_receipts_created':False,'gate_evidence_files_created':False,
  'release_signing_performed':False,'final_seal':'NOT_ISSUED',
  'next_actions':[
   'G01: obtain independently validated original upstream provider builds and source-lock-matched receipts, not maintainer assertions',
   'G02: capture two independently validated fresh Devtool negative-test runs at a fixed source commit',
   'Do not copy Q14 summary to sb_g01_provider_builds.json or sb_g02_source.json',
   'Only original CFS1 gate evaluators may determine eligibility']}

def markdown(data:dict)->str:
 lines=['# Skybind SB-Q15 — Independent G01/G02 Evidence Readiness','',
  '**Final seal: NOT_ISSUED** — read-only preparation, never gate promotion.','',
  'CI recheck: `'+data['owner_signed_ci']['status']+'`',
  '']
 if data['errors']:lines.extend(['### Q14 material errors','']+['- '+x for x in data['errors']]+[''])
 lines.extend(['| Gate | Actual evaluator | Missing or blocking evidence |','|---|---|---|'])
 for gate,rec in data['gate_contracts'].items():
  lines.append('| '+gate+' | '+rec['actual']+' | '+', '.join(rec['actual_reasons']).replace('|','/')+' |')
 lines.extend(['','### Next steps','']+['- '+x for x in data['next_actions']])
 return '\n'.join(lines)+'\n'

def safe_write(out:Path,name:str,content:bytes)->None:
 if out.is_symlink() or not out.is_dir():raise ValueError('OUTPUT_DIRECTORY_INVALID')
 dst=out/name
 if dst.is_symlink():raise ValueError('OUTPUT_SYMLINK_FORBIDDEN')
 fd,tmp=tempfile.mkstemp(prefix='.q15-',dir=str(out))
 try:
  with os.fdopen(fd,'wb') as f:f.write(content);f.flush();os.fsync(f.fileno())
  os.replace(tmp,dst)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)

def main(argv=None)->int:
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--repository',type=Path,default=ROOT)
 ap.add_argument('--q14-report',type=Path,default=Path('/storage/emulated/0/Download/skybind-q14-summary.json'))
 ap.add_argument('--artifact-root',type=Path,default=Path('/storage/emulated/0/Download/skybind-q14-run-38336604093'))
 ap.add_argument('--trusted-public-key',type=Path,default=Path.home()/'.config/skybind/trust/q14-ci-public.pem')
 ap.add_argument('--output-dir',type=Path,default=Path('/storage/emulated/0/Download'))
 ap.add_argument('--reauthenticate-github',action='store_true')
 ns=ap.parse_args(argv)
 result=evaluate(ns.repository,ns.q14_report,ns.artifact_root,ns.trusted_public_key,reauthenticate=ns.reauthenticate_github)
 safe_write(ns.output_dir,'skybind-q15-summary.json', (json.dumps(result,indent=2,sort_keys=True)+'\n').encode())
 safe_write(ns.output_dir,'skybind-q15-summary.md',markdown(result).encode())
 print('SB-Q15',result['owner_signed_ci']['status'],'G01',result['gate_contracts']['SB-G01']['actual'],
       'G02',result['gate_contracts']['SB-G02']['actual'],'seal',result['final_seal'])
 return 0 if not result['errors'] else 3
if __name__=='__main__':raise SystemExit(main())
