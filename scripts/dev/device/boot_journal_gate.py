#!/usr/bin/env python3
"""Two-stage RAW Android reboot evidence; never initiates a reboot or mutates a queue.

Prepare -> operator-authorized reboot -> verify. Stage data is hashed, bounded,
source-bound and saved in Downloads. Absent proof is BLOCKED, not PASS.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import subprocess
import sys
import time
import zipfile

from api_acceptance import BIN, DeviceRPC, HEX_ID

OUT = Path('/storage/emulated/0/Download/Skybind-API-Device-Tests')
PRIVATE = {
    'event_spool':'/data/adb/skybind/events/events-v1.json',
    'jobs_state':'/data/adb/skybind/jobs/jobs-v1.json',
    'queued_edits':'/data/adb/skybind/offline/writes/edits-v1.json',
    'offline_reviews':'/data/adb/skybind/offline/writes/review-v1.json',
}
STATUSES = ('PASS','FAIL','BLOCKED')

class GateError(Exception): pass

def digest(data):return hashlib.sha256(data).hexdigest()
def utc():return dt.datetime.now(dt.timezone.utc).isoformat()
def root(command, timeout=20, max_bytes=65536):
    """Only constant commands or fixed validated args; don't return raw stderr."""
    try:
        p=subprocess.run(['su','-c',command],capture_output=True,timeout=timeout,check=False)
    except (OSError,subprocess.TimeoutExpired) as e:raise GateError('root command unavailable') from e
    if p.returncode or len(p.stdout)>max_bytes:raise GateError('root read-only command failed or oversized response')
    return p.stdout.decode('utf-8','replace').strip()

def boot_identity():
    value=root('/system/bin/cat /proc/sys/kernel/random/boot_id')
    if not re.fullmatch(r'[0-9a-fA-F-]{36}',value):raise GateError('invalid kernel boot identifier')
    return digest(value.lower().encode())

def file_hash(path):
    if path not in PRIVATE.values():raise GateError('unsupported protected path')
    # Do not follow a swapped-in symlink or export file body; root-private
    # snapshots are read-only and must remain under the stable state root.
    command='if [ -L {p} ]; then exit 2; elif [ ! -e {p} ]; then printf ABSENT; elif [ -f {p} ]; then /system/bin/sha256sum {p}; else exit 3; fi'.format(p=shlex.quote(path))
    output=root(command)
    if output=='ABSENT':return {'present':False}
    found=re.fullmatch(r'([a-f0-9]{64})\s+\S+',output)
    if not found:raise GateError('private file digest invalid')
    return {'present':True,'sha256':found.group(1)}

def api_snapshot(rpc):
    response=rpc.call('operation.events','query',{'cursor':0,'limit':1,'wait_ms':0})['result']
    if not isinstance(response,dict):raise GateError('event API result unavailable')
    latest=response.get('latest_cursor')
    if type(latest) is not int or latest<0:raise GateError('event latest cursor missing')
    jobs=rpc.call('jobs.status','query',{})['result']
    if not isinstance(jobs,dict) or not isinstance(jobs.get('runs'),list):raise GateError('jobs.status invalid')
    states={r.get('id'):r.get('state') for r in jobs['runs'] if isinstance(r,dict) and
            isinstance(r.get('id'),str) and HEX_ID.fullmatch(r['id'])}
    # Never export user job IDs, names, endpoints or reasons.
    counts={s:sum(state==s for state in states.values()) for s in ('RUNNING','QUEUED','INTERRUPTED','COMPLETED','FAILED','CANCELLED')}
    return {'events':{'latest':latest,'oldest':response.get('oldest_cursor'),
                      'gap':bool(response.get('gap')),'degraded':bool(response.get('degraded'))},
            'job_counts':counts},states

def capture(rpc,owned_id=None):
    result={'captured_at_utc':utc(), 'boot_id_sha256':boot_identity(),
            'installed_binary_sha256':rpc.installed_binary_hash(),
            'ce_available':root('/system/bin/getprop sys.user.0.ce_available').lower(),
            'boot_completed':root('/system/bin/getprop sys.boot_completed'),
            'private_hashes':{key:file_hash(value) for key,value in PRIVATE.items()}}
    if not result['installed_binary_sha256'] or not re.fullmatch(r'[a-f0-9]{64}',result['installed_binary_sha256']):
        raise GateError('installed binary hash not observable')
    summary,states=api_snapshot(rpc)
    result['api']=summary
    if owned_id:
        result['owned_job_state']=states.get(owned_id,'NOT_IN_HISTORY')
        try:
            p=rpc.call('operation.events','query',{'cursor':0,'limit':64,'operation_id':owned_id,'wait_ms':0})['result']
            result['owned_interruption_event_seen']=bool(isinstance(p,dict) and isinstance(p.get('events'),list) and
                any(isinstance(e,dict) and e.get('type')=='job.interrupted' for e in p['events']))
            result['owned_event_gap']=bool(p.get('gap')) if isinstance(p,dict) else True
        except Exception:
            result['owned_interruption_event_seen']=False
            result['owned_event_gap']=True
    return result

def decide(before,after,owned=False):
    cases=[]
    def case(name,status,note):cases.append({'test':name,'status':status,'note':note})
    if before['boot_id_sha256']==after['boot_id_sha256']:
        case('New kernel boot identity','BLOCKED','device has not rebooted between captures')
    else:case('New kernel boot identity','PASS','distinct kernel boot IDs')
    if before['installed_binary_sha256']!=after['installed_binary_sha256']:
        case('Installed binary unchanged','FAIL','binary changed during reboot gate')
    else:case('Installed binary unchanged','PASS','installed ELF retained')
    prev=before['api']['events']; now=after['api']['events']
    if now['latest']<prev['latest']:
        case('Durable event sequence','FAIL','event sequence moved backwards')
    elif now.get('degraded') or prev.get('degraded'):
        case('Durable event sequence','BLOCKED','event persistence degraded')
    else:case('Durable event sequence','PASS','event sequence not regressed')
    for key in ('queued_edits','offline_reviews'):
        a,b=before['private_hashes'][key],after['private_hashes'][key]
        if a!=b:case(key+' preserved','FAIL','offline metadata changed across reboot')
        elif a.get('present'):case(key+' preserved','PASS','offline metadata digest retained')
        else:case(key+' preserved','BLOCKED','no existing file to prove retention')
    if after['ce_available'] not in ('true','1') or after['boot_completed']!='1':
        case('Boot and CE readiness','BLOCKED','device not fully booted/unlocked for this capture')
    else:case('Boot and CE readiness','PASS','boot and CE property available at capture time only')
    if not owned:
        case('Interrupted owned job recovery','BLOCKED','no test-owned running job identified; user jobs untouched')
    elif before.get('owned_job_state')!='RUNNING':
        case('Interrupted owned job recovery','BLOCKED','test-owned job was not RUNNING at prepare time')
    elif after.get('owned_job_state')=='INTERRUPTED' and after.get('owned_interruption_event_seen'):
        case('Interrupted owned job recovery','PASS','owned job persisted and interruption event observed')
    elif after.get('owned_job_state')=='INTERRUPTED':
        case('Interrupted owned job recovery','BLOCKED','state persisted but interruption event not demonstrated')
    elif after.get('owned_job_state') in ('RUNNING','QUEUED','COMPLETED'):
        case('Interrupted owned job recovery','FAIL','running job not reconciled to interrupted after boot')
    else:case('Interrupted owned job recovery','BLOCKED','owned job missing/other state; inspect private raw evidence')
    case('Independent test-owned job provenance','BLOCKED','requires run-specific creation receipt tied to disposable workspace')
    return cases

def write_json_exclusive(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_symlink() or path.exists():raise GateError('evidence path already exists')
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as f:
        json.dump(obj,f,sort_keys=True,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())

def source_info():
    repo=Path(__file__).resolve().parents[3]
    try:
        head=subprocess.run(['git','rev-parse','HEAD'],cwd=repo,capture_output=True,text=True,timeout=5,check=True).stdout.strip()
        status=subprocess.run(['git','status','--porcelain'],cwd=repo,capture_output=True,text=True,timeout=5,check=True).stdout
        if not re.fullmatch(r'[0-9a-f]{40}',head):raise ValueError()
    except (OSError,ValueError,subprocess.SubprocessError):return {'commit':None,'tree_clean':None}
    return {'commit':head,'tree_clean':not bool(status)}

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    pre=sub.add_parser('prepare');pre.add_argument('--owned-job-id',default=os.environ.get('SKYBIND_QA_OWNED_JOB_ID',''))
    post=sub.add_parser('verify');post.add_argument('--prepare-file',type=Path,default=Path(os.environ.get('SKYBIND_QA_BOOT_PREPARE','/nonexistent')));post.add_argument('--owned-job-id',default=os.environ.get('SKYBIND_QA_OWNED_JOB_ID',''))
    parser.add_argument('--output-dir',type=Path,default=OUT)
    opts=parser.parse_args(argv)
    try:
        if opts.action=='prepare':
            owned_id=opts.owned_job_id.strip()
            if owned_id and not HEX_ID.fullmatch(owned_id):raise GateError('invalid owned job identity')
            snap=capture(DeviceRPC(),owned_id or None)
            document={'schema_version':1,'kind':'SKYBIND_BOOT_JOURNAL_PREPARE','status':'PREPARED_NOT_QUALIFIED',
                      'session':secrets.token_hex(16),'source':source_info(), 'snapshot':snap,
                      'owned_id_sha256':digest(owned_id.encode()) if owned_id else None,
                      'limitations':['no automatic reboot','offline metadata read-only','not release evidence by itself']}
            path=opts.output_dir/('skybind-boot-pre-'+document['session']+'.json')
            write_json_exclusive(path,document)
            print('PREPARED: '+str(path)+'\nReboot is NOT performed. Re-run the verify stage only after an authorized reboot.')
            return 0
        p=opts.prepare_file
        if not p.is_file() or p.is_symlink() or p.stat().st_size>20000:raise GateError('prepare JSON unavailable or oversized')
        before=json.loads(p.read_text('utf-8'))
        if before.get('kind')!='SKYBIND_BOOT_JOURNAL_PREPARE' or before.get('schema_version')!=1 or not re.fullmatch(r'[a-f0-9]{32}',str(before.get('session',''))):
            raise GateError('invalid prior prepare receipt')
        owned_id=opts.owned_job_id.strip()
        if owned_id and not HEX_ID.fullmatch(owned_id):raise GateError('invalid owned job identity')
        if bool(owned_id)!=bool(before.get('owned_id_sha256')) or (owned_id and digest(owned_id.encode())!=before['owned_id_sha256']):
            raise GateError('test-owned job identity not provided or mismatched')
        after=capture(DeviceRPC(),owned_id or None)
        checks=decide(before['snapshot'],after,owned=bool(owned_id))
        document={'schema_version':1,'kind':'SKYBIND_BOOT_JOURNAL_VERIFY','qualification':'RAW_UNATTESTED',
                  'session':before['session'],'source':source_info(), 'prepared_source':before.get('source'),
                  'before':before['snapshot'],'after':after,'cases':checks,
                  'counts':{status:sum(x['status']==status for x in checks) for status in STATUSES},
                  'notes':['Full interrupted-job test needs a distinct explicitly owned running job',
                           'No auto-reboot, offline edits, remote transfer, or queue mutation executed']}
        output=opts.output_dir/('skybind-boot-verify-'+before['session']+'.json')
        write_json_exclusive(output,document)
        with zipfile.ZipFile(output.with_suffix('.zip'),'x',compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(p,arcname=p.name);archive.write(output,arcname=output.name)
        print('REPORT: '+str(output)+'\nCOUNTS: '+str(document['counts']))
        return 1 if document['counts']['FAIL'] else 0
    except (GateError,ValueError,KeyError,TypeError,OSError,json.JSONDecodeError) as err:
        print('BOOT GATE BLOCKED: '+str(err)[:160],file=sys.stderr)
        return 3
    except Exception:
        print('BOOT GATE BLOCKED: unexpected collector exception (private details suppressed)',file=sys.stderr)
        return 3

if __name__=='__main__':sys.exit(main())
