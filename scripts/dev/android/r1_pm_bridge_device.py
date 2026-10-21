#!/usr/bin/env python3
"""Opt-in multi-case, source-bound R1 Android->Go PM channel device acceptance.

Three independent live cases: approved BKX signing, denied wrong signer,
denied wrong Skybind authority UID. This does NOT issue or exercise grants,
BKX client IPC, chrootctl archive or Restic. No M2/M3 retests.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import uuid
import os

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(ROOT/'scripts/devtool'))
import m2_live_device as live
import ci_artifacts_device as ci

HEX=re.compile(r'[0-9a-f]{64}\Z')
CONTEXT=re.compile(r'u:r:[A-Za-z0-9_]+:s[0-9]+(?::c[0-9]+(?:,c[0-9]+)*)?\Z')
REPO='Mikeyphw/skybind'
ARTIFACT='skybind-r1-pm-bridge-android-arm64-unqualified'
AGENT_NEGATIVE_CLASS='io.github.mikeyphw.skybind.R1PMBridgeAgentTest'
AGENT_NEGATIVE_TESTS=frozenset(('deniesUnknownConsumer', 'deniesUninstalledOrWrongUid', 'deniesInvalidNonce', 'deniesUnknownFields'))

class Blocked(Exception):pass

def shell(cmd:list[str],timeout=30,ok=True):
    p=subprocess.run(cmd,timeout=timeout,capture_output=True,text=True)
    if ok and p.returncode!=0:raise Blocked('COMMAND_FAILED_'+cmd[0])
    return p

def load_hosted_binary(run_id:int,sha:str,dest:Path)->Path:
    # GitHub CLI fetches an artifact from the authenticated remote run. Local
    # JSON alone cannot authorize its provenance: confirm the run's exact SHA.
    run=shell(['gh','api',f'repos/{REPO}/actions/runs/{run_id}'])
    detail=json.loads(run.stdout)
    if detail.get('head_sha')!=sha or detail.get('conclusion')!='success' or detail.get('name')!='Skybind R1 Android-to-Go PM bridge (unqualified diagnostic)':
        raise Blocked('GO_DIAGNOSTIC_RUN_MISMATCH')
    shell(['gh','run','download',str(run_id),'-R',REPO,'--name',ARTIFACT,'--dir',str(dest)],timeout=120)
    meta=json.loads((dest/'source.json').read_text())
    if meta!={'schema':'skybind-r1-pm-diag-artifact-v1','source_sha':sha,'r1_provider_qualified':False,'release_qualified':False}:
        raise Blocked('GO_DIAGNOSTIC_MANIFEST_MISMATCH')
    binary=dest/'skybind-r1-pm-android-arm64'
    sums=(dest/'SHA256SUMS.txt').read_text().strip().split()
    if len(sums)!=2 or sums[1]!=binary.name or not HEX.fullmatch(sums[0]) or hashlib.sha256(binary.read_bytes()).hexdigest()!=sums[0]:
        raise Blocked('GO_DIAGNOSTIC_BYTES_MISMATCH')
    binary.chmod(0o700)
    return binary

def interpret_agent_negative_instrumentation(output: str) -> dict:
    """Accept complete four-test instrumentation evidence only, not exit-code zero.

    The Android instrumentation runner sometimes returns shell status 0 for a
    failed test run; require both its final code and exact per-test receipts.
    """
    tests=re.findall(r'^INSTRUMENTATION_STATUS: test=(.+)\r?$',output,re.MULTILINE)
    counts=re.findall(r'^INSTRUMENTATION_STATUS: numtests=(\d+)\r?$',output,re.MULTILINE)
    codes=re.findall(r'^INSTRUMENTATION_STATUS_CODE: (-?\d+)\r?$',output,re.MULTILINE)
    final=re.findall(r'^INSTRUMENTATION_CODE: (-?\d+)\r?$',output,re.MULTILINE)
    # AndroidJUnitRunner ordinarily reports each test twice (start + finish),
    # but some runner versions omit the duplicate test label. Accept both
    # shapes only when all four expected test identities are accounted for.
    from collections import Counter
    observed=Counter(tests)
    normal_names=(len(tests)==8 and all(observed[t]==2 for t in AGENT_NEGATIVE_TESTS))
    reduced_names=(len(tests)==4 and all(observed[t]==1 for t in AGENT_NEGATIVE_TESTS))
    if (not (normal_names or reduced_names) or len(observed)!=len(AGENT_NEGATIVE_TESTS) or
        not counts or any(c!=str(len(AGENT_NEGATIVE_TESTS)) for c in counts) or
        codes!=[item for _ in AGENT_NEGATIVE_TESTS for item in ('1','0')] or
        final!=['-1'] or 'FAILURES!!!' in output or 'INSTRUMENTATION_FAILED' in output):
        raise Blocked('ANDROID_AGENT_NEGATIVE_INSTRUMENTATION_INCOMPLETE')
    return {'state':'PASS_R1_PM_AGENT_FOUR_NEGATIVE_TESTS','count':len(AGENT_NEGATIVE_TESTS),
            'tests':sorted(AGENT_NEGATIVE_TESTS)}

def run_agent_negative_instrumentation(serial: str) -> dict:
    # Runs only the Skybind test APK; never opens BKX or accesses a backup.
    command=['adb','-s',serial,'shell','am','instrument','-w','-r',
       '-e','class',AGENT_NEGATIVE_CLASS,
       'io.github.mikeyphw.skybind.test/androidx.test.runner.AndroidJUnitRunner']
    p=shell(command,timeout=160,ok=False)
    if p.returncode!=0:
        raise Blocked('ANDROID_AGENT_NEGATIVE_INSTRUMENTATION_COMMAND_FAILED')
    return interpret_agent_negative_instrumentation(p.stdout+'\n'+p.stderr)

def one_case(binary:Path, pin_uid:int, pin_context:str,bkx_uid:int,bkx_signer:str,serial:str,restart:bool)->dict:
    argv=[str(binary), '--skybind-uid',str(pin_uid), '--skybind-context',pin_context,
          '--bkx-uid',str(bkx_uid),'--bkx-signer',bkx_signer]
    # su sees only fixed commands plus individually shell-quoted, validated
    # operator pins. No client input is forwarded to the native daemon.
    cmd='exec '+' '.join(map(shlex.quote,argv))
    process=subprocess.Popen(['su','-c',cmd],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        # Listener prints readiness to stderr before waiting for the app's
        # unprivileged onStart. Avoid launching before it is ready.
        import threading,queue
        q=queue.Queue()
        def read_ready():
            try:q.put(process.stderr.readline())
            except Exception:q.put('')
        threading.Thread(target=read_ready,daemon=True).start()
        try:message=q.get(timeout=8)
        except queue.Empty:raise Blocked('ROOT_DIAGNOSTIC_NO_READY_SIGNAL')
        if 'R1 authority listener started' not in message:
            output,_=process.communicate(timeout=3)
            raise Blocked('ROOT_DIAGNOSTIC_START_FAILED:'+output[:60])
        if restart:
            shell(['adb','-s',serial,'shell','am','force-stop','io.github.mikeyphw.skybind'])
            shell(['adb','-s',serial,'shell','am','start','-n','io.github.mikeyphw.skybind/.MainActivity'])
        output,errors=process.communicate(timeout=24)
        lines=[x.strip() for x in output.splitlines() if x.strip().startswith('{')]
        if not lines:raise Blocked('ROOT_DIAGNOSTIC_NO_MACHINE_RECEIPT')
        value=json.loads(lines[-1])
        if value.get('schema')!='skybind-r1-android-to-go-pm-v1':raise Blocked('ROOT_DIAGNOSTIC_SCHEMA_MISMATCH')
        if process.returncode not in (0,2):raise Blocked('ROOT_DIAGNOSTIC_UNEXPECTED_EXIT')
        return value
    finally:
        if process.poll() is None:
            process.terminate()
            try:process.wait(timeout=2)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        if process.stdout:process.stdout.close()
        if process.stderr:process.stderr.close()

def perform(args):
    result={'schema':'skybind-r1-platform-bridge-three-case-v1','status':'BLOCKED','reason':None,
            'captured_utc':datetime.now(timezone.utc).isoformat(),
            'pm_channel_qualified':False,'bkx_process_attested':False,'chrootctl_process_attested':False,
            'grants_issued':False,'external_provider_qualified':False,'release_qualified':False,
            'm2_m3_device_retests_run':False,'cases':{}, 'android_agent_negative_instrumentation':None}
    try:
        if not args.restart_skybind:
            raise Blocked('SKYBIND_RESTART_REQUIRED_FOR_THREE_INDEPENDENT_CASES')
        if not HEX.fullmatch(args.bkx_signer) or args.bkx_uid<10000 or args.skybind_uid<10000 or args.bkx_uid==args.skybind_uid or not CONTEXT.fullmatch(args.skybind_context):
            raise Blocked('INVALID_OPERATOR_APPROVAL')
        sha=live.current_source();result['source_sha']=sha
        if args.expected_sha!=sha:raise Blocked('SOURCE_IDENTITY_MISMATCH')
        apk=live.github(args.apk_run_id,sha)
        pair=Path.home()/'.cache/skybind'/f'hosted-{args.apk_run_id}'
        ci.obtain_pair(args.apk_run_id,apk['id'],pair)
        manifest=live.verify_candidate(pair,args.apk_run_id,sha,live.read_pin())
        serial=live.choose_device(args.serial)
        live.installed_pair(serial,manifest,live.read_pin())
        result['installed_pair_verified']=True
        result['android_agent_negative_instrumentation']=run_agent_negative_instrumentation(serial)
        with tempfile.TemporaryDirectory(prefix='skybind-r1-go-') as td:
            binary=load_hosted_binary(args.go_run_id,sha,Path(td))
            wrong='0'*64 if args.bkx_signer!='0'*64 else '1'*64
            cases=[('positive',args.skybind_uid,args.bkx_signer,'PASS_R1_AUTHENTICATED_PM_CHANNEL_ONLY'),
                   ('wrong_signer',args.skybind_uid,wrong,'BKX_SIGNER_OR_UID_DENIED'),
                   ('wrong_authority_uid',args.skybind_uid+1,args.bkx_signer,'AUTHORITY_PEER_NOT_ATTESTED')]
            for name,uid,signer,expect in cases:
                rec=one_case(binary,uid,args.skybind_context,args.bkx_uid,signer,serial,args.restart_skybind)
                result['cases'][name]={'state':rec['State'] if 'State' in rec else rec.get('state'),
                                       'reason':rec['Reason'] if 'Reason' in rec else rec.get('reason'),
                                       'pm_channel_authenticated':rec.get('pm_channel_authenticated',False)}
                state=result['cases'][name]['state'];reason=result['cases'][name]['reason']
                if rec.get('consumer_broker_qualified') is not False or rec.get('grants_issued') is not False or rec.get('m3_device_retests_run') is not False:
                    raise Blocked('DIAGNOSTIC_RECEIPT_OVERCLAIMS_QUALIFICATION')
                if rec.get('schema')!='skybind-r1-android-to-go-pm-v1':
                    raise Blocked('DIAGNOSTIC_RECEIPT_SCHEMA_MISMATCH')
                if (rec.get('pm_channel_authenticated') is not (name != 'wrong_authority_uid') or
                    rec.get('bkx_signer_approved') is not (name == 'positive')):
                    raise Blocked('DIAGNOSTIC_RECEIPT_INCONSISTENT_FLAGS_'+name)
                if name=='positive' and state!=expect:raise Blocked('POSITIVE_NOT_QUALIFIED')
                if name!='positive' and (state!='BLOCKED' or reason!=expect):raise Blocked('NEGATIVE_GATE_MISMATCH_'+name)
            result['status']='PASS_R1_ANDROID_TO_GO_PM_THREE_CASES_PLUS_FOUR_AGENT_NEGATIVES'
            result['pm_channel_qualified']=True
    except (Blocked,live.Blocked,ci.QualificationError,ValueError,OSError,KeyError,subprocess.TimeoutExpired,FileNotFoundError) as exc:
        result['reason']=(exc.reason if isinstance(exc,live.Blocked) else str(exc))[:140]
    output=args.output_root
    if output.is_symlink():raise SystemExit('unsafe receipt destination')
    output.mkdir(mode=0o700,parents=True,exist_ok=True)
    path=output/('r1-pm-bridge-'+uuid.uuid4().hex+'.json')
    with path.open('x') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
    path.chmod(0o600)
    result['receipt']=str(path)
    print(json.dumps(result,sort_keys=True))
    return 0 if result['status'].startswith('PASS_') else 2

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--apk-run-id',type=int,required=True)
    p.add_argument('--go-run-id',type=int,required=True)
    p.add_argument('--expected-sha',required=True)
    p.add_argument('--serial',default='emulator-5554')
    p.add_argument('--bkx-uid',type=int,required=True)
    p.add_argument('--bkx-signer',required=True)
    p.add_argument('--skybind-uid',type=int,required=True)
    p.add_argument('--skybind-context',required=True)
    p.add_argument('--restart-skybind',action='store_true',help='REQUIRED: restart only the Skybind UI for each case; never launch BKX or chrootctl')
    p.add_argument('--output-root',type=Path,default=Path.home()/'.local/state/skybind/r1-pm-bridge')
    raise SystemExit(perform(p.parse_args()))
if __name__=='__main__':main()
