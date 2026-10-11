#!/usr/bin/env python3
"""SB-G01 fresh evidence gate. Never treats source fixtures as upstream proof."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
EVIDENCE=ROOT/'build/evidence/sb_g01_provider_builds.json'
LOCK=ROOT/'scripts/dev/runtime/source.lock.json'
REQUIRE=('SB-O01','SB-O02','SB-O03','SB-O04','SB-O05')

def sha(path:Path)->str:
 return hashlib.sha256(path.read_bytes()).hexdigest()

def evaluate(evidence:Path=EVIDENCE, root:Path=ROOT)->dict:
 missing=[]
 lockpath=root/'scripts/dev/runtime/source.lock.json'
 if not lockpath.is_file():return {'gate':'SB-G01','status':'BLOCKED','assurance':'NOT_ATTESTED','reasons':['source lock missing']}
 lock=json.loads(lockpath.read_text())
 new=lock['newfuture'];b=lock['bclone']
 for group,key in [('newfuture','archive_sha256'),('bclone','commit'),('bclone','ndk_revision'),('bclone','go_version')]:
  if not lock[group].get(key):missing.append('unfilled trust pin '+group+'.'+key)
 if not evidence.is_file():missing.append('real-provider build evidence missing')
 else:
  try:
   obj=json.loads(evidence.read_text())
   if obj.get('qualification')!='REAL_PINNED_PROVIDER_BUILD' or obj.get('schema_version')!=1:missing.append('invalid evidence qualification')
   if obj.get('source_lock_sha256')!=sha(lockpath):missing.append('pin or evidence drift')
   if sorted(obj.get('overlay_ids',[]))!=list(REQUIRE):missing.append('overlay closure incomplete')
   if obj.get('device_qualification') is not False:missing.append('source-only gate cannot claim Android device')
   for provider in ('newfuture','bclone'):
    records=obj.get('providers',{}).get(provider,[])
    if len(records)!=2:missing.append(provider+': requires independent two clean builds')
    else:
     hashes=[]
     for rec in records:
      if not isinstance(rec,dict) or rec.get('test_fixture') is not False or rec.get('verified_official_source') is not True:missing.append(provider+': build provenance not independently verified');continue
      path=Path(rec.get('archive_path',''))
      # No path supplied by WebUI/client. Gate is executed by trusted developer only.
      if not path.is_absolute() or not path.is_file():missing.append(provider+': archive missing');continue
      if rec.get('sha256')!=sha(path):missing.append(provider+': artifact digest does not match');continue
      hashes.append(rec['sha256'])
      if rec.get('source_commit')!=obj.get('source_commit'):missing.append(provider+': source commit mismatch')
     if len(hashes)==2 and hashes[0]!=hashes[1]:missing.append(provider+': non-reproducible outputs')
   if obj.get('helper_hash_newfuture')!=obj.get('helper_hash_bclone') or not obj.get('helper_hash_newfuture'):missing.append('NewFuture FUSE helper parity unproven')
   if obj.get('webui_visual_parity')=='PASS' or obj.get('android_device_pass') is True:missing.append('source gate cannot claim unrelated evidence')
  except (OSError,TypeError,ValueError,KeyError) as e: missing.append('invalid evidence: '+str(e))
 # A build manifest alone does not independently authenticate GitHub asset
 # provenance; require explicit externally validated source attestation.
 return {'gate':'SB-G01','status':'BLOCKED' if missing else 'SOURCE_BUILD_PASS','assurance':'NOT_ATTESTED' if missing else 'SOURCE_ONLY','reasons':missing,'android_device':'NOT_ATTESTED','final_seal':'NOT_ISSUED'}

def main():
 p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args()
 result=evaluate();print(json.dumps(result,indent=2,sort_keys=True))
 return 0 if result['status']=='SOURCE_BUILD_PASS' else 3
if __name__=='__main__':sys.exit(main())
