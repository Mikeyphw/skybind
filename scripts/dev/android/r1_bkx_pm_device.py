#!/usr/bin/env python3
"""Opt-in on-device BKX PackageManager observation, NOT broker qualification.

Uses a source-bound, authenticated hosted Skybind instrumentation APK pair and
independently approved signer/UID pins. Never installs, grants, starts BKX,
reads credentials, or enables a consumer socket. The signer argument must not
be minted from a caller-submitted JSON claim.
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

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(ROOT/'scripts/devtool'))
import m2_live_device as live
import ci_artifacts_device as ci

CASE='io.github.mikeyphw.skybind.R1BKXInstalledPackageAcceptanceTest#liveApprovedBKXSigningAndWrongSignerRejection'
HEX=re.compile(r'[0-9a-f]{64}\Z')

def interpret_instrumentation(out: str):
    if 'SKYBIND_R1_BKX_PM_NOT_REQUESTED' in out or 'INSTRUMENTATION_STATUS_CODE: -3' in out:
        return 'BLOCKED', 'TEST_WAS_SKIPPED'
    for marker in ('SKYBIND_R1_BLOCKED_OPERATOR_SIGNER_PIN_MISSING','SKYBIND_R1_BLOCKED_OPERATOR_UID_PIN_MISSING','SKYBIND_R1_BLOCKED_INVALID_OPERATOR_PIN'):
        if marker in out: return 'BLOCKED', marker
    for marker in ('SKYBIND_R1_FAILED_BKX_UID','SKYBIND_R1_FAILED_BKX_PACKAGE','SKYBIND_R1_FAILED_WRONG_SIGNER_ACCEPTED'):
        if marker in out: return 'FAILED', marker
    if (re.findall(r'INSTRUMENTATION_CODE:\s*(-?\d+)',out)==['-1'] and
        re.findall(r'INSTRUMENTATION_STATUS_CODE:\s*(-?\d+)',out)==['1','0'] and
        'INSTRUMENTATION_STATUS: test=liveApprovedBKXSigningAndWrongSignerRejection' in out and
        'INSTRUMENTATION_STATUS: numtests=1' in out and 'FAILURES!!!' not in out):
        return 'PASS_R1_BKX_PLATFORM_PM_OBSERVATION_ONLY', None
    return 'FAILED','INSTRUMENTATION_INCOMPLETE_OR_UNCLASSIFIED'

def perform(args):
    report=dict(schema='skybind-r1-bkx-pm-observation-v1',state='BLOCKED',reason=None,
      collected_at_utc=datetime.now(timezone.utc).isoformat(),github_run_id=args.run_id,
      trusted_android_to_go_bridge_qualified=False,installed_bkx_process_attested=False,
      chrootctl_process_attested=False,grants_issued=False,external_provider_qualified=False,
      release_qualified=False,installation_performed=False,automatic_app_launch=False)
    try:
        if not HEX.fullmatch(args.approved_signer) or not 10000<=args.approved_uid<=2**31-1:
            raise live.Blocked('INVALID_OPERATOR_APPROVAL')
        sha=live.current_source();report['source_sha']=sha
        if args.expected_sha != sha:raise live.Blocked('SOURCE_IDENTITY_MISMATCH')
        artifact=live.github(args.run_id,sha);report['artifact_id']=artifact['id']
        folder=Path.home()/'.cache/skybind'/f'hosted-{args.run_id}'
        ci.obtain_pair(args.run_id,artifact['id'],folder)
        manifest=live.verify_candidate(folder,args.run_id,sha,live.read_pin())
        serial=live.choose_device(args.serial)
        report['device_serial_sha256']=hashlib.sha256(serial.encode()).hexdigest()
        live.installed_pair(serial,manifest,live.read_pin())
        report['installed_pair_verified']=True
        cmd=('shell','am','instrument','-w','-r',
             '-e','skybind.r1.bkx.pm.live','true',
             '-e','skybind.r1.bkx.approved.sha256',args.approved_signer,
             '-e','skybind.r1.bkx.approved.uid',str(args.approved_uid),
             '-e','class',CASE,
             'io.github.mikeyphw.skybind.test/androidx.test.runner.AndroidJUnitRunner')
        p=live.adb(serial,*cmd,timeout=160,ok=False)
        state,reason=interpret_instrumentation(p.stdout+'\n'+p.stderr)
        report['state'],report['reason']=state,reason
        report['pm_scope_passed']=state.startswith('PASS_')
    except (live.Blocked,ci.QualificationError,ValueError,OSError,KeyError) as exc:
        report['reason']=(exc.reason if isinstance(exc,live.Blocked) else str(exc))[:140]
    path=args.output_root/('r1-bkx-pm-'+uuid.uuid4().hex+'.json')
    if args.output_root.is_symlink(): raise SystemExit('unsafe receipt destination symlink')
    args.output_root.mkdir(parents=True,mode=0o700,exist_ok=True)
    with path.open('x') as f: json.dump(report,f,indent=2,sort_keys=True);f.write('\n')
    path.chmod(0o600)
    report['receipt']=str(path)
    print(json.dumps(report,sort_keys=True))
    return 0 if report['state'].startswith('PASS_') else 2

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-id',type=int,required=True)
    p.add_argument('--expected-sha',required=True)
    p.add_argument('--serial',default='emulator-5554')
    p.add_argument('--approved-uid',type=int,required=True)
    p.add_argument('--approved-signer',required=True,help='Operator approved DER signing cert SHA256, not an auto-trusted observation')
    p.add_argument('--output-root',type=Path,default=Path.home()/'.local/state/skybind/r1-platform')
    raise SystemExit(perform(p.parse_args()))

if __name__=='__main__':main()
