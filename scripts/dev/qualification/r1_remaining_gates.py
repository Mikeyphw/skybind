#!/usr/bin/env python3
"""Independent-scope R1/M2/M3/Q16 evidence crosswalk, never a release seal.

Inputs are locally supplied receipts, not independently authenticated attestations.
Every promotion beyond previously qualified scopes must be established by a
separate trusted gate; external_provider_qualified and release_qualified are
therefore always false in this descriptive crosswalk.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import uuid

R1_CASES=frozenset(('no_token','positive_capabilities','positive_version',
                    'positive_remotes','positive_list','positive_size',
                    'wrong_operation','wrong_remote','wrong_path','wrong_process',
                    'revocation','expiry'))
RETEST_EXPECTED={
    'live':'PASS_M2_L1_LIVE_READ_BROWSE_REBIND',
    'ui-live':'PASS_M2_L2_LIVE_UI_READONLY_RECOVERY',
    'negative-live':'PASS_M2_L3_READONLY_NEGATIVE_BOUNDARIES',
    'transport-live':'PASS_M2_L3_APP_OWNED_TRANSPORT_RECOVERY',
    'm3-preview-live':'PASS_M3_REAL_DAEMON_PREVIEW_ONLY',
    'm3-execute-live':'PASS_M3_DISPOSABLE_CHECK_COMPLETION',
    'm3-cancel-live':'PASS_M3_DISPOSABLE_OWNED_CANCEL',
    'm3-copy-live':'PASS_M3_DISPOSABLE_COPY_RECONCILED',
    'm2-process-live':'PASS_M2_L3_APP_PROCESS_COLD_LAUNCH',
}
RETEST_CASES=frozenset(RETEST_EXPECTED)
HEX40=re.compile(r'^[a-f0-9]{40}$')
MAX_FILE=256 * 1024

class Rejected(Exception):
    pass


def read(path:Path) -> tuple[dict,str]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_FILE:
        raise Rejected('MISSING_UNSAFE_OR_OVERSIZED_INPUT')
    b=path.read_bytes()
    try: obj=json.loads(b)
    except (ValueError,UnicodeDecodeError) as exc: raise Rejected('INPUT_JSON_INVALID') from exc
    if not isinstance(obj,dict): raise Rejected('INPUT_OBJECT_REQUIRED')
    return obj,hashlib.sha256(b).hexdigest()


def valid_r1(doc:dict, remote:str) -> bool:
    cases=doc.get('bkx_test_cases')
    return (doc.get('schema') == 'skybind-r1-bkx-device-consolidated-v1'
       and doc.get('state') == 'PASS_R1_BKX_AND_CHROOTCTL_NARROW_LIVE_ACCEPTANCE_ONLY'
       and doc.get('remote') == remote and isinstance(cases,dict)
       and set(cases) == R1_CASES and all(cases[k] == 'PASS' for k in R1_CASES)
       and all(doc.get(key) is True for key in (
           'bkx_five_positive_machine_qualified','bkx_debug_separate_process_replay_qualified',
           'bkx_live_kernel_peer_attested','bkx_negative_socket_qualified',
           'chrootctl_nine_security_cases_qualified'))
       and doc.get('release_qualified') is False
       and doc.get('external_provider_qualified') is False)


def valid_retests(doc:dict) -> bool:
    cases=doc.get('cases')
    return (doc.get('schema')=='skybind-m2-m3-fresh-batch-v1'
        and doc.get('state')=='PASS_M2_M3_FRESH_NINE_LANE_AUTOMATED_RETEST_ONLY'
        and doc.get('profile')=='full'
        and isinstance(doc.get('source_sha'),str)
        and HEX40.fullmatch(doc['source_sha']) is not None
        and isinstance(doc.get('github_run_id'),int) and doc['github_run_id']>0
        and doc.get('installed_pair_verified') is True
        and doc.get('m2_m3_device_retests_run') is True
        and doc.get('external_provider_qualified') is False
        and doc.get('release_qualified') is False
        and isinstance(cases,dict) and set(cases)==RETEST_CASES
        and all(isinstance(cases[k],dict) and
                isinstance(cases[k].get('state'),str) and
                cases[k]['state']==RETEST_EXPECTED[k] for k in RETEST_CASES))


def describe_q16(doc:dict|None) -> str:
    if doc is None: return 'NOT_SUBMITTED'
    if (doc.get('campaign')=='SB-Q16'
        and doc.get('status')=='TWO_REAL_PROVIDER_LANES_VERIFIED_RAW_NOT_INDEPENDENTLY_ATTESTED'
        and doc.get('independent_custody') is False
        and doc.get('original_upstream_origin_independently_attested') is False
        and doc.get('gate_evidence_generated') is False
        and doc.get('final_seal')=='NOT_ISSUED'):
        return 'RAW_TWO_LANE_BYTES_READY_FOR_INDEPENDENT_REVIEW_NOT_ATTESTED'
    return 'Q16_NOT_ESTABLISHED'


def reconcile(r1:dict|None, retests:dict|None, q16:dict|None, remote:str) -> dict:
    r1_pass=r1 is not None and valid_r1(r1,remote)
    retest_pass=retests is not None and valid_retests(retests)
    q16_state=describe_q16(q16)
    return {'schema':'skybind-r1-remaining-qualification-crosswalk-v1',
            'captured_utc':datetime.now(timezone.utc).isoformat(),
            'remote':remote,
            'narrow_r1_21_case_security_qualified_from_supplied_receipt':r1_pass,
            'm2_m3_nine_fresh_automated_retests_qualified_from_supplied_receipt':retest_pass,
            'q16_upstream_provider_evidence':q16_state,
            'independent_provider_origin_and_builder_custody_qualified':False,
            'external_provider_qualified':False,'release_qualified':False,
            'g01_independent_evaluation':'PENDING_INDEPENDENT_AUTHORITY',
            'm2_m3_device_retests_run':retest_pass,
            'next_gate':('OBTAIN_R1_21_CASE_SECURITY_RECEIPT' if not r1_pass else
                         'OBTAIN_M2_M3_NINE_LANE_DEVICE_RECEIPT' if not retest_pass else
                         'OBTAIN_Q16_TWO_LANE_RAW_PROVIDER_EVIDENCE' if q16_state=='NOT_SUBMITTED' else
                         'INDEPENDENT_G01_ORIGIN_AND_BUILDER_CUSTODY_REVIEW'),
            'state':('PASS_R1_NARROW_AND_M2_M3_FRESH_SCOPE_ONLY' if r1_pass and retest_pass else
                     'BLOCKED_REMAINING_QUALIFICATION_EVIDENCE_INCOMPLETE')}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--r1-receipt',type=Path,required=True)
    p.add_argument('--m2-m3-receipt',type=Path)
    p.add_argument('--q16-summary',type=Path)
    p.add_argument('--remote',default='GDDavys')
    p.add_argument('--output-dir',type=Path,default=Path.home()/'.local/state/skybind/r1-final-report')
    a=p.parse_args(argv)
    if not re.fullmatch('[A-Za-z][A-Za-z0-9_-]{0,62}',a.remote):
        print('BLOCKED_R1_CROSSWALK_INVALID_REMOTE',file=sys.stderr);return 2
    try:
        r1,r1sha=read(a.r1_receipt)
        retest,rsha=read(a.m2_m3_receipt) if a.m2_m3_receipt else (None,None)
        q16,qsha=read(a.q16_summary) if a.q16_summary else (None,None)
        report=reconcile(r1,retest,q16,a.remote)
        report['evidence_sha256']={'r1':r1sha, 'm2_m3':rsha, 'q16':qsha}
        out=a.output_dir
        if out.is_symlink():raise Rejected('OUTPUT_DIRECTORY_SYMLINK')
        out.mkdir(parents=True,exist_ok=True,mode=0o700)
        if out.stat().st_mode & 0o077:raise Rejected('OUTPUT_DIRECTORY_PERMISSIONS_UNSAFE')
        target=out/('r1-crosswalk-'+uuid.uuid4().hex+'.json')
        report['receipt']=str(target)
        with target.open('x') as f:
            json.dump(report,f,sort_keys=True,indent=2);f.write('\n')
        target.chmod(0o600)
    except (OSError,Rejected) as e:
        print('BLOCKED_R1_CROSSWALK_'+str(e)[:80],file=sys.stderr)
        return 2
    print(json.dumps({'state':report['state'],'receipt':report['receipt'],
                      'next_gate':report['next_gate'],
                      'external_provider_qualified':False,'release_qualified':False},sort_keys=True))
    return 0 if report['state'].startswith('PASS_') else 2

if __name__=='__main__':
    raise SystemExit(main())
