#!/usr/bin/env python3
"""Personal Skybind Android acceptance runner. No install/mount/network writes.

Usage: python3 scripts/dev/integration/m0_m8_device_tests.py -h
Requires Termux Python 3, standard library only; records *manual* tests truthfully.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import zipfile

CASES = Path(__file__).with_name('m0_m8_device_cases.json')
STATES = ('NOT_RUN', 'PASS', 'FAIL', 'BLOCKED', 'SKIP')
VERSION = 1

def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')

def load(path):
    with Path(path).open(encoding='utf-8') as f:
        return json.load(f)

def write_json(path, data):
    path = Path(path)
    temp = path.with_name('.'+path.name+'.tmp')
    with temp.open('w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)

def read_run(folder):
    folder = Path(folder).expanduser().resolve(strict=True)
    run = load(folder / 'results.json')
    if run.get('schema_version') != VERSION or not isinstance(run.get('cases'),dict):
        raise ValueError('Unexpected run JSON schema')
    return folder,run

def new_run(out,mount):
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,62}',mount):
        raise ValueError('Invalid mount name')
    catalog=load(CASES)
    stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    folder=Path(out).expanduser().resolve() / ('skybind-device-'+stamp)
    folder.mkdir(parents=True,exist_ok=False)
    now=utc()
    run={'schema_version':VERSION,'project':'skybind','created_at':now,'updated_at':now,
         'mount':mount,'installed_build_sha256':None,'android_sdk':None,
         'source':'manual results, device probe statuses; no secret-bearing stdout saved',
         'cases':{c['id']:{'status':'NOT_RUN','notes':'','seconds':None,'updated_at':None} for c in catalog['cases']},
         'probes':[], 'cautions':['Use disposable remote/files','Never publish raw rclone.conf, backup JSON, logcat or remote paths']}
    write_json(folder/'results.json',run)
    (folder/'README.txt').write_text('Skybind personal acceptance results. Cases are marked only by you.\n'
         'Do NOT add credentials, remote URLs, or confidential filenames to notes.\n'
         'The probe stores exit status and elapsed time, never command output.\n',encoding='utf-8')
    report(folder, run, verbose=False)
    print(folder)

def report(folder, run, verbose=True):
    cat=load(CASES)
    totals={s:0 for s in STATES}
    rows=[]
    for c in cat['cases']:
        status=run['cases'][c['id']]['status']
        totals[status]+=1
        rows.append({'id':c['id'],'milestone':c['milestone'],'title':c['title'],'status':status})
    summary={'schema_version':1,'generated_at':utc(),'mount':run['mount'],
             'installed_build_sha256':run.get('installed_build_sha256'),
             'android_sdk':run.get('android_sdk'), 'counts':totals,'all_pass':totals['PASS']==len(rows),
             'cases':rows,'probes':run.get('probes',[]),
             'note':'PASS records human confirmation, not independently authenticated proof.'}
    write_json(folder/'summary.json',summary)
    lines=['# Skybind real-device results','',f'UTC generated: {summary["generated_at"]}',
           f'Mount: `{run["mount"]}` (replace or redact before public sharing)','',
           ' '.join(f'{key}: **{val}**' for key,val in totals.items()),'',
           '| Case | What | Result |','|---|---|---|']
    for r in rows:lines.append(f'| {r["id"]} | {r["title"]} | {r["status"]} |')
    lines+=['','## Failures, blockers and notes','']
    for r in rows:
        item=run['cases'][r['id']]
        if item['status'] not in ('PASS','NOT_RUN') or item['notes']:
            lines.append(f'- **{r["id"]} [{item["status"]}]**: {item["notes"] or "No details recorded."}')
    lines+=['','No passwords, rclone.conf, complete backups, or unredacted logs are included automatically.','']
    (folder/'summary.md').write_text('\n'.join(lines),encoding='utf-8')
    if verbose:
        print(f'Cases: {len(rows)} · '+', '.join(f'{k} {v}' for k,v in totals.items()))
        print(f'Reports: {folder}/summary.md ; {folder}/summary.json')

def record(folder,run,case,status,notes,seconds):
    if case not in run['cases']:raise ValueError('Unknown case ID: '+case)
    if len(notes)>600:raise ValueError('Notes exceed 600 characters')
    if seconds is not None and (seconds<0 or seconds>86400):raise ValueError('Invalid duration')
    run['cases'][case]={'status':status,'notes':notes,'seconds':seconds,'updated_at':utc()}
    run['updated_at']=utc()
    write_json(folder/'results.json',run)
    report(folder,run)

def probe(folder,run):
    """Read-only installed CLI checks; command stdout/stderr not stored."""
    sb='/data/adb/modules/skybind/system/bin/skybind'
    checks=[('version',sb+' version'),('static-runtime',sb+' runtime-status'),
            ('capabilities',sb+' capabilities'),('mount-list',sb+' mount list'),
            ('jobs-list',sb+' jobs list')]
    for label,command in checks:
        start=time.monotonic()
        try:
            p=subprocess.run(['su','-c',command],capture_output=True,text=True,timeout=20)
            result='PASS' if p.returncode==0 else 'FAIL'
            code=p.returncode
        except (OSError,subprocess.TimeoutExpired):
            result='BLOCKED';code=None
        elapsed=round(time.monotonic()-start,2)
        run['probes'].append({'name':label,'status':result,'exit_code':code,'elapsed_seconds':elapsed,'at':utc()})
        print(label, result, f'({elapsed}s)')
    # Collect only SDK version; no Android device IDs, build fingerprints or paths.
    try:
        x=subprocess.run(['getprop','ro.build.version.sdk'],capture_output=True,text=True,timeout=5)
        if x.returncode==0 and x.stdout.strip().isdigit():run['android_sdk']=x.stdout.strip()
    except (OSError,subprocess.TimeoutExpired):pass
    # No filesystem mutation: read-only hash for matching installed build with release receipt.
    try:
        x=subprocess.run(['su','-c',f'sha256sum {sb}'],capture_output=True,text=True,timeout=15)
        if x.returncode==0 and re.fullmatch(r'[0-9a-f]{64}',x.stdout.split()[0]):
            run['installed_build_sha256']=x.stdout.split()[0]
    except (OSError, subprocess.TimeoutExpired,IndexError):pass
    run['updated_at']=utc()
    write_json(folder/'results.json',run)
    report(folder,run)

def package(folder,run):
    report(folder,run)
    filenames=['README.txt','results.json','summary.json','summary.md']
    files={f:(folder/f).read_bytes() for f in filenames}
    sums=''.join(f'{hashlib.sha256(data).hexdigest()}  {name}\n' for name,data in sorted(files.items()))
    files['SHA256SUMS']=sums.encode()
    out=folder.with_suffix('.zip')
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=7) as z:
        for name,data in sorted(files.items()):z.writestr(name,data)
    print('Evidence ZIP:',out)
    print('ZIP SHA256:',hashlib.sha256(out.read_bytes()).hexdigest())

def main(argv=None):
    p=argparse.ArgumentParser(description='Skybind M0–M8 personal real-device checks (no automatic writes)')
    sp=p.add_subparsers(dest='command',required=True)
    a=sp.add_parser('init',help='Create a fresh JSON checklist in Downloads')
    a.add_argument('--mount',required=True,help='Name of disposable mount')
    a.add_argument('--out',default='/storage/emulated/0/Download/Skybind-Device-Tests')
    for name in ['show','probe','report','bundle']:
        sub=sp.add_parser(name)
        sub.add_argument('--run',required=True,help='Existing run directory')
    a=sp.add_parser('record',help='Record ONE actual human-observed result')
    a.add_argument('--run',required=True);a.add_argument('--case',required=True)
    a.add_argument('--status',choices=STATES[1:],required=True)
    a.add_argument('--notes',default='');a.add_argument('--seconds',type=float)
    a=sp.add_parser('selftest',help='Exercise JSON/report/ZIP without a phone')
    opts=p.parse_args(argv)
    try:
        if opts.command=='init':new_run(opts.out,opts.mount);return 0
        if opts.command=='selftest':
            with tempfile.TemporaryDirectory() as base:
                new_run(base,'testmount')
                folder=next(Path(base).iterdir());folder,run=read_run(folder)
                case=next(iter(run['cases']))
                record(folder,run,case,'PASS','test fixture only',1.0)
                folder,run=read_run(folder)
                assert run['cases'][case]['status']=='PASS'
                package(folder,run)
                assert folder.with_suffix('.zip').exists()
            print('selftest PASS');return 0
        folder,run=read_run(opts.run)
        if opts.command=='show':
            cat=load(CASES)
            for c in cat['cases']:
                print(f'{c["id"]:8} {run["cases"][c["id"]]["status"]:8} {c["title"]}')
        elif opts.command=='record':record(folder,run,opts.case,opts.status,opts.notes,opts.seconds)
        elif opts.command=='probe':probe(folder,run)
        elif opts.command=='report':report(folder,run)
        elif opts.command=='bundle':package(folder,run)
        return 0
    except (OSError,ValueError,KeyError,json.JSONDecodeError) as e:
        print('ERROR:',e,file=sys.stderr);return 2

if __name__=='__main__':sys.exit(main())
