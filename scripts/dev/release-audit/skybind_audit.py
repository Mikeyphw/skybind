#!/usr/bin/env python3
"""Independent, fail-closed C06 audit. Never signs or seals an artifact.

Source evidence is not device qualification. Raw probe receipts and user-supplied
JSON cannot promote a release; independent Devtool gates own that decision.
"""
from __future__ import annotations
import argparse,hashlib,json,pathlib,re,sys
ROOT=pathlib.Path(__file__).resolve().parents[3]
REQUIRED=['SB-G01','SB-G02','SB-G03','SB-G04','SB-G05','SB-G06','SB-G07','SB-G08']

def blocked_report(repo: pathlib.Path=ROOT)->dict:
    problems=[]
    try:
        lock=json.loads((repo/'scripts/dev/runtime/source.lock.json').read_text())
        # The audit is a denial gate, not a cryptographic upstream attestor.
        # Malformed JSON shapes must produce a blocked report, never a traceback.
        if not isinstance(lock,dict):
            raise TypeError('provider lock must be an object')
        provider=lock['newfuture']
        b=lock['bclone']
        if not isinstance(provider,dict) or not isinstance(b,dict):
            raise TypeError('provider records must be objects')
        pin=provider.get('archive_sha256')
        if not isinstance(pin,str) or not re.fullmatch(r'[0-9a-f]{64}',pin):
            problems.append('NEWFUTURE_ARCHIVE_SHA256_UNPINNED')
        if not isinstance(b.get('commit'),str) or not re.fullmatch(r'[0-9a-f]{40}',b['commit']):
            problems.append('BCLONE_COMMIT_UNPINNED')
        if any(not isinstance(b.get(key),str) or not b[key].strip()
               for key in ('ndk_revision','go_version')):
            problems.append('BCLONE_TOOLCHAIN_UNPINNED')
    except (OSError,ValueError,KeyError,TypeError): problems.append('PROVIDER_LOCK_UNTRUSTWORTHY')
    try:
        plan=json.loads((repo/'docs/roadmap/SKYBIND_DEVTOOL_OVERLAY_INDEX.json').read_text())
        statuses=[x['status'] for x in plan['artifact_sequence']]
        if statuses[:6] != ['SOURCE_IMPLEMENTED_NOT_PROMOTED']*6 or statuses[6:]!=['SOURCE_IMPLEMENTED_NOT_PROMOTED','PLANNED']:
            problems.append('C06_SOURCE_OBLIGATION_INCOMPLETE')
        if plan['starting_position']['gate_qualification'] != {'SB-G01':'BLOCKED','SB-G02':'BLOCKED'}:
            problems.append('GATE_STATE_NOT_AUTHENTIC')
    except (OSError,ValueError,KeyError,TypeError): problems.append('CAMPAIGN_INDEX_INVALID')
    problems += [
      'ANDROID_APP_VISIBILITY_NOT_ATTESTED',
      'PHYSICAL_DEVICE_MANAGER_MATRIX_NOT_ATTESTED',
      'UPSTREAM_BOTH_PROVIDERS_NOT_QUALIFIED',
      'ORIGINAL_WEBUI_BROWSER_GOLDENS_NOT_ATTESTED',
      'ANDROID_ENDURANCE_FAULT_MATRIX_NOT_ATTESTED',
      'INDEPENDENT_DEVTOOL_GATES_NOT_PASSED',
    ]
    return {'schema_version':1,'product':'skybind','overlay':'SB-C06',
            'status':'BLOCKED','assurance':'SOURCE_CANDIDATE_ONLY',
            'milestone_gates':{g:'NOT_QUALIFIED' for g in REQUIRED},
            'final_seal':'NOT_ISSUED','reasons':sorted(set(problems))}

def main():
    p=argparse.ArgumentParser();p.add_argument('--repository',type=pathlib.Path,default=ROOT)
    a=p.parse_args()
    print(json.dumps(blocked_report(a.repository),sort_keys=True))
    return 3
if __name__=='__main__':sys.exit(main())
