#!/usr/bin/env python3
"""Source-bound R1 chrootctl installed-process diagnostic; never mutate backups.

Runs 3 live cases ONLY with explicit --live and independently approved module
manifest seal, SELinux label, and an already-running installed chrootctl PID.
Default mode verifies the hosted diagnostic artifact and source identity only.
No client grants, socket activation, backup execution or module installation.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import uuid

REPO = 'Mikeyphw/skybind'
ARTIFACT = 'skybind-r1-consumer-diagnostics-unqualified'
WORKFLOW = 'Skybind R1 consumer gateway and module diagnostics (unqualified)'
HEX = re.compile(r'[0-9a-f]{64}\Z')
COMMIT = re.compile(r'[0-9a-f]{40}\Z')
CONTEXT = re.compile(r'u:r:[A-Za-z0-9_]+:s[0-9]+(?::c[0-9]+(?:,c[0-9]+)*)?\Z')
BINARIES = ('skybind-r1-gateway-android-arm64', 'skybind-r1-module-check-android-arm64')
ROOT = Path(__file__).resolve().parents[3]

class Blocked(Exception):
    pass

def command(argv, *, timeout=60):
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)

def expected_source():
    p=command(['git','-C',str(ROOT),'rev-parse','HEAD'])
    if p.returncode or not COMMIT.fullmatch(p.stdout.strip()):
        raise Blocked('LOCAL_SOURCE_UNVERIFIED')
    return p.stdout.strip()

def load_artifact(run_id, sha, dest):
    r=command(['gh','api',f'repos/{REPO}/actions/runs/{run_id}'])
    if r.returncode:
        raise Blocked('GITHUB_RUN_UNAVAILABLE')
    try:
        record=json.loads(r.stdout)
    except (ValueError, TypeError):
        raise Blocked('GITHUB_RUN_UNPARSEABLE')
    if record.get('head_sha')!=sha or record.get('conclusion')!='success' or record.get('name')!=WORKFLOW or record.get('event')!='workflow_dispatch':
        raise Blocked('GITHUB_SOURCE_OR_WORKFLOW_MISMATCH')
    r=command(['gh','run','download',str(run_id),'-R',REPO,'--name',ARTIFACT,'--dir',str(dest)],timeout=160)
    if r.returncode:
        raise Blocked('DIAGNOSTIC_ARTIFACT_DOWNLOAD_FAILED')
    try:
        source=dest/'source.json'
        if source.is_symlink() or not source.is_file() or source.stat().st_size>4096:
            raise Blocked('DIAGNOSTIC_MANIFEST_INVALID')
        meta=json.loads(source.read_text())
        if meta!={'schema':'skybind-r1-consumer-diagnostic-artifact-v1','source_sha':sha,'external_provider_qualified':False,'release_qualified':False}:
            raise Blocked('DIAGNOSTIC_MANIFEST_MISMATCH')
        sums=dest/'SHA256SUMS.txt'
        if sums.is_symlink() or not sums.is_file() or sums.stat().st_size>2048:
            raise Blocked('DIAGNOSTIC_SHA_MANIFEST_INVALID')
        actual={}
        for line in sums.read_text().splitlines():
            pair=line.split()
            if len(pair)!=2 or not HEX.fullmatch(pair[0]) or pair[1] not in BINARIES or pair[1] in actual:
                raise Blocked('DIAGNOSTIC_SHA_MANIFEST_INVALID')
            actual[pair[1]]=pair[0]
        if set(actual)!=set(BINARIES):
            raise Blocked('DIAGNOSTIC_SHA_MANIFEST_INCOMPLETE')
        for name, digest in actual.items():
            f=dest/name
            if f.is_symlink() or not f.is_file() or f.stat().st_size<4096 or f.stat().st_size>80*1024*1024:
                raise Blocked('DIAGNOSTIC_BINARY_INVALID')
            if hashlib.sha256(f.read_bytes()).hexdigest()!=digest:
                raise Blocked('DIAGNOSTIC_BINARY_SHA_MISMATCH')
        # Fixed names only: never execute downloaded paths provided by a manifest.
        binary=dest/'skybind-r1-module-check-android-arm64'
        binary.chmod(0o700)
        return binary
    except (json.JSONDecodeError, UnicodeError, OSError) as e:
        raise Blocked('DIAGNOSTIC_ARTIFACT_INVALID') from e

def check_receipt(raw, code, mode):
    try:
        lines=[line.strip() for line in raw.splitlines() if line.strip()]
        if len(lines)!=1:
            raise Blocked('MODULE_DIAGNOSTIC_INVALID_JSON_COUNT')
        receipt=json.loads(lines[0])
    except (ValueError, TypeError):
        raise Blocked('MODULE_DIAGNOSTIC_INVALID_JSON')
    if not isinstance(receipt,dict) or receipt.get('schema')!='skybind-r1-live-chrootctl-process-v1' or \
       receipt.get('grants_issued') is not False or receipt.get('external_provider_qualified') is not False or \
       receipt.get('release_qualified') is not False:
        raise Blocked('MODULE_DIAGNOSTIC_OVERCLAIMS')
    state=receipt.get('state');attested=receipt.get('chrootctl_process_attested');reason=receipt.get('reason')
    if mode=='positive':
        if code !=0 or state!='PASS_R1_LIVE_CHROOTCTL_MODULE_PROCESS_ONLY' or attested is not True or reason not in (None,''):
            raise Blocked('CHROOTCTL_LIVE_PROCESS_NOT_ATTESTED')
    else:
        if code !=2 or state!='BLOCKED' or attested is not False or reason!='CHROOTCTL_LIVE_SEAL_OR_SELINUX_NOT_ATTESTED':
            raise Blocked('CHROOTCTL_NEGATIVE_NOT_DENIED_'+mode.upper())
    return {'state':state,'reason':reason,'process_attested':attested}

def module_case(binary, pid, seal, label, name):
    if name not in ('positive','wrong_seal','wrong_context'):
        raise Blocked('UNSUPPORTED_DIAGNOSTIC_CASE')
    # Path resides in private temporary directory. The operator, not any
    # consumer, chooses the approved inputs. No rclone operation is invoked.
    args=[str(binary),'--pid',str(pid),'--approved-manifest-sha256',seal,'--approved-selinux',label]
    command_line='exec '+' '.join(shlex.quote(x) for x in args)
    run=command(['su','-c',command_line],timeout=12)
    return check_receipt(run.stdout,run.returncode,name)

def run(args):
    receipt={'schema':'skybind-r1-chrootctl-process-device-v1',
             'captured_utc':datetime.now(timezone.utc).isoformat(),
             'state':'BLOCKED','reason':None,'github_run_id':args.run_id,
             'hosted_diagnostic_verified':False,'chrootctl_process_attested':False,
             'grants_issued':False,'external_provider_qualified':False,
             'release_qualified':False,'bkx_apk_adapter_qualified':False,
             'android_selinux_consumer_socket_qualified':False,
             'm2_m3_device_retests_run':False,'cases':{}}
    try:
        if not COMMIT.fullmatch(args.expected_sha):
            raise Blocked('INVALID_EXPECTED_SOURCE')
        sha=expected_source();receipt['source_sha']=sha
        if sha!=args.expected_sha:
            raise Blocked('SOURCE_IDENTITY_MISMATCH')
        if args.live and (not args.operator_approve or not args.pid or args.pid<=0 or args.pid>2**31-1 or
                         not HEX.fullmatch(args.approved_manifest_sha256 or '') or
                         not CONTEXT.fullmatch(args.approved_selinux or '')):
            raise Blocked('INVALID_INDEPENDENT_OPERATOR_APPROVAL')
        with tempfile.TemporaryDirectory(prefix='skybind-r1-chrootctl-') as td:
            binary=load_artifact(args.run_id,sha,Path(td))
            receipt['hosted_diagnostic_verified']=True
            if not args.live:
                receipt['state']='PASS_R1_DIAGNOSTIC_ARTIFACT_PREFLIGHT_ONLY'
            else:
                seal=args.approved_manifest_sha256
                bad_seal='0'*64 if seal!='0'*64 else '1'*64
                wrong_label='u:r:untrusted_app:s0' if args.approved_selinux!='u:r:untrusted_app:s0' else 'u:r:su:s0'
                for name,pin,lbl in (('positive',seal,args.approved_selinux),('wrong_seal',bad_seal,args.approved_selinux),('wrong_context',seal,wrong_label)):
                    receipt['cases'][name]=module_case(binary,args.pid,pin,lbl,name)
                receipt['chrootctl_process_attested']=True
                receipt['state']='PASS_R1_CHROOTCTL_LIVE_SEAL_THREE_CASES_ONLY'
    except (Blocked,subprocess.TimeoutExpired,OSError) as e:
        receipt['reason']=str(e)[:160]
    out=args.output_root
    if out.is_symlink():
        raise SystemExit('unsafe receipt directory')
    out.mkdir(mode=0o700,parents=True,exist_ok=True)
    path=out/('r1-chrootctl-process-'+uuid.uuid4().hex+'.json')
    with path.open('x') as f:
        json.dump(receipt,f,indent=2,sort_keys=True);f.write('\n')
    path.chmod(0o600)
    receipt['receipt']=str(path)
    print(json.dumps(receipt,sort_keys=True))
    return 0 if receipt['state'].startswith('PASS_') else 2

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-id',type=int,required=True)
    p.add_argument('--expected-sha',required=True)
    p.add_argument('--live',action='store_true',help='Opt-in three-case diagnostic against already-running chrootctl PID')
    p.add_argument('--operator-approve',action='store_true',help='Required for live test')
    p.add_argument('--pid',type=int,help='Already running approved chrootctl process PID; never auto-launch')
    p.add_argument('--approved-manifest-sha256',default='',help='Independently approved newly installed module package manifest digest')
    p.add_argument('--approved-selinux',default='',help='Independently approved live process SELinux label')
    p.add_argument('--output-root',type=Path,default=Path.home()/'.local/state/skybind/r1-chrootctl-process')
    raise SystemExit(run(p.parse_args()))
if __name__=='__main__':main()
