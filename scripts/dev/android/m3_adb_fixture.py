#!/usr/bin/env python3
"""Explicit, same-ADB-device M3 disposable job fixtures.

Never creates/starts/cancels a run; only typed jobs.status/preview/apply.
The sole mutable root is Download/.skybind-m3-{disposable,copy} on the selected
Android device. No local Termux daemon, filesystem or package is mutated.
Preflight/inspect are read-only. --apply is mandatory to create one fixture.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

import m3_disposable_fixture as check
import m3_copy_fixture as copy

ADB = re.compile(r'[A-Za-z0-9._:-]{1,120}\Z')
BASE = '/storage/emulated/0/Download'
CLI = '/data/adb/modules/skybind/system/bin/skybind'

class Blocked(Exception):
    pass

def need(cond, why):
    if not cond:
        raise Blocked(why)

def run_adb(serial, *args, timeout=90):
    need(bool(ADB.fullmatch(serial)), 'ADB_SERIAL_INVALID')
    try:
        p = subprocess.run(['adb','-s',serial,*args],capture_output=True,text=True,
                           timeout=timeout,check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise Blocked('TARGET_ADB_TRANSPORT_UNAVAILABLE') from exc
    need(p.returncode == 0, 'TARGET_ADB_COMMAND_FAILED')
    return p.stdout.strip()

def target(serial):
    devices=run_adb(serial,'get-state')
    need(devices == 'device','TARGET_ADB_NOT_READY')
    fingerprint=run_adb(serial,'shell','getprop','ro.build.fingerprint')
    need(bool(fingerprint) and len(fingerprint) < 512,'TARGET_FINGERPRINT_UNAVAILABLE')
    uid=run_adb(serial,'shell','su','-c','/system/bin/id -u')
    need(uid.strip()=='0','TARGET_ROOT_UID_NOT_VERIFIED')
    return hashlib.sha256(fingerprint.encode()).hexdigest()

def root(serial, command, timeout=90):
    need(len(command)<160000,'TARGET_COMMAND_TOO_LARGE')
    return run_adb(serial,'shell','su','-c',command,timeout=timeout)

def shelltest(serial, expression):
    # No user-controlled shell substitutions; caller supplies only constants.
    try:
        r=subprocess.run(['adb','-s',serial,'shell','su','-c',expression],
                         capture_output=True,text=True,timeout=35,check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise Blocked('TARGET_SHELL_TEST_UNAVAILABLE') from exc
    return r.returncode==0

def rpc(serial, op, args):
    need(op in ('jobs.status','jobs.preview','jobs.apply'),'OPERATION_NOT_ALLOWLISTED')
    command=' '.join(shlex.quote(x) for x in
        [CLI,'operation',op,json.dumps(args,separators=(',',':'))])
    out=root(serial,command,timeout=40)
    try: obj=json.loads(out)
    except ValueError as exc: raise Blocked('TARGET_DAEMON_NON_JSON') from exc
    need(type(obj) is dict and obj.get('ok') is True and
         isinstance(obj.get('result'),dict),'TARGET_DAEMON_REFUSED_'+op.replace('.','_'))
    return obj['result']

def registry(serial):
    status=rpc(serial,'jobs.status',{})
    reg=status.get('registry')
    need(type(reg) is dict and reg.get('schema_version')==1 and
         type(reg.get('revision')) is int and reg['revision']>=0, 'TARGET_REGISTRY_INVALID')
    jobs=reg.get('jobs')
    if jobs is None:
        need('jobs' in reg,'TARGET_REGISTRY_JOBS_MISSING')
        jobs=[]
    need(type(jobs) is list and all(type(j) is dict for j in jobs),'TARGET_JOBS_INVALID')
    need(not any(j.get('kind')=='sync' for j in jobs),'TARGET_SYNC_JOB_REGISTRY_REFUSED')
    runs=status.get('runs')
    need(type(runs) is list,'TARGET_RUN_HISTORY_INVALID')
    for kind, name, expected in [('check',check.NAME,check.definition()),
                                 ('copy',copy.NAME,copy.definition())]:
        entries=[j for j in jobs if j.get('name')==name]
        need(len(entries)<=1 and all(all(j.get(k)==v for k,v in expected.items())
                                     for j in entries),'TARGET_'+kind.upper()+'_IDENTITY_CONFLICT')
        need(not any(type(r) is dict and r.get('name')==name and
                 r.get('state') in ('RUNNING','QUEUED') for r in runs),
             'TARGET_'+kind.upper()+'_RUN_ACTIVE')
    return {'schema_version':1,'revision':reg['revision'],'jobs':jobs},runs

def fixture_paths(kind, files, phase):
    need(kind in ('check','copy'),'KIND_INVALID')
    need(phase in ('prepared','complete'),'PHASE_INVALID')
    need(type(files) is int and (64<=files<=check.MAX_FILES if kind=='check'
             else copy.MIN_FILES<=files<=copy.MAX_FILES),'FILE_COUNT_INVALID')
    root=check.ROOT if kind=='check' else copy.ROOT
    expected={str(root),str(root/'source'),str(root/'destination')}
    hashes={}
    if kind=='check':
        marker=json.dumps({'schema':'skybind-m3-disposable-v1','count':files},sort_keys=True)+'\n'
        name=check.MARKER
        hashes[str(root/name)]=hashlib.sha256(marker.encode()).hexdigest()
        for i in range(files):
            for folder in ('source','destination'):
                hashes[str(root/folder/f'sample-{i:05d}.bin')]=hashlib.sha256(check.payload(i)).hexdigest()
    else:
        marker=json.dumps({'schema':'skybind-m3-copy-v1','count':files},sort_keys=True)
        hashes[str(root/copy.MARKER)]=hashlib.sha256(marker.encode()).hexdigest()
        hashes[str(root/'destination'/copy.SENTINEL)]=hashlib.sha256(b'SKYBIND-M3-COPY-DO-NOT-OVERWRITE\n').hexdigest()
        for i in range(files):
            name=f'copy-{i:05d}.bin'
            hashes[str(root/'source'/name)]=hashlib.sha256(copy.payload(i)).hexdigest()
            if phase=='complete':
                hashes[str(root/'destination'/name)]=hashlib.sha256(copy.payload(i)).hexdigest()
    return root,expected,hashes

def scan(serial, kind, files, phase='prepared'):
    root_path,dirs,hashes=fixture_paths(kind,files,phase)
    loc=shlex.quote(str(root_path))
    need(shelltest(serial,f'test -d {loc} && test ! -L {loc}'), 'TARGET_FIXTURE_ROOT_ABSENT_OR_LINK')
    # Exact membership: no extra directory, file, or link of any type is acceptable.
    observed=set(root(serial,'/system/bin/find '+loc+' -print',timeout=90).splitlines())
    need(observed==dirs|set(hashes),'TARGET_FIXTURE_FOREIGN_OR_MISSING_ENTRY')
    symlinks=root(serial,'/system/bin/find '+loc+' -type l -print')
    need(symlinks=='','TARGET_FIXTURE_SYMLINK')
    for directory in dirs:
        need(shelltest(serial,'test -d '+shlex.quote(directory)+' && test ! -L '+shlex.quote(directory)),
             'TARGET_FIXTURE_DIRECTORY_UNSAFE')
    # SHA256 utility is invoked with exact, generated paths and no unchecked globbing.
    paths=sorted(hashes)
    command='/system/bin/sha256sum '+' '.join(shlex.quote(p) for p in paths)
    lines=root(serial,command,timeout=150).splitlines()
    actual={}
    for line in lines:
        match=re.fullmatch(r'([0-9a-f]{64})\s+\*?(.+)',line)
        need(match is not None,'TARGET_FIXTURE_SHA_FORMAT')
        digest,p=match.groups()
        need(p not in actual,'TARGET_FIXTURE_DUPLICATE_SHA_ROW')
        actual[p]=digest
    need(actual==hashes,'TARGET_FIXTURE_HASH_OR_MEMBERSHIP_MISMATCH')
    value={'kind':kind,'phase':phase,'count':files,'target_files_verified':len(hashes),
           'target_digest_sha256':hashlib.sha256(''.join(p+':'+h+'\n' for p,h in sorted(hashes.items())).encode()).hexdigest()}
    if kind=='copy':
        content=hashlib.sha256()
        for i in range(files):
            name=f'copy-{i:05d}.bin'
            content.update(name.encode()+b'\0'+hashlib.sha256(copy.payload(i)).digest())
        value.update(expected_content_sha256=content.hexdigest(),source_verified=True,
                     destination_verified=(phase=='complete'),sentinel_preserved=True)
    return value

def recorded_count(serial,kind):
    root_path=check.ROOT if kind=='check' else copy.ROOT
    marker=check.MARKER if kind=='check' else copy.MARKER
    path=shlex.quote(str(root_path/marker))
    text=root(serial,'/system/bin/cat '+path)
    try: obj=json.loads(text)
    except ValueError as exc: raise Blocked('TARGET_MARKER_NON_JSON') from exc
    need(obj.get('schema')==('skybind-m3-disposable-v1' if kind=='check' else 'skybind-m3-copy-v1')
         and type(obj.get('count')) is int,'TARGET_MARKER_INVALID')
    return obj['count']

def verify(serial,kind,phase='prepared'):
    count=recorded_count(serial,kind)
    return scan(serial,kind,count,phase)

def stage(serial,kind,files):
    path,_,_=fixture_paths(kind,files,'prepared')
    loc=shlex.quote(str(path))
    # Must not install into any preexisting fixture. Never delete on failure.
    need(shelltest(serial,f'test ! -e {loc} && test ! -L {loc}'), 'TARGET_FIXTURE_ALREADY_EXISTS')
    with tempfile.TemporaryDirectory(prefix='skybind-target-fixture-') as tmp:
        parent=Path(tmp)
        staged=parent/path.name
        (staged/'source').mkdir(parents=True)
        (staged/'destination').mkdir(parents=True)
        if kind=='check':
            for i in range(files):
                filename=f'sample-{i:05d}.bin'
                b=check.payload(i)
                (staged/'source'/filename).write_bytes(b)
                (staged/'destination'/filename).write_bytes(b)
            (staged/check.MARKER).write_text(json.dumps({'schema':'skybind-m3-disposable-v1',
                                               'count':files},sort_keys=True)+'\n')
        else:
            for i in range(files):
                (staged/'source'/f'copy-{i:05d}.bin').write_bytes(copy.payload(i))
            (staged/'destination'/copy.SENTINEL).write_bytes(b'SKYBIND-M3-COPY-DO-NOT-OVERWRITE\n')
            (staged/copy.MARKER).write_text(json.dumps({'schema':'skybind-m3-copy-v1',
                                                       'count':files},sort_keys=True))
        # Push exactly one isolated test-owned directory to the selected target.
        run_adb(serial,'push',str(staged),BASE+'/',timeout=200)
    return scan(serial,kind,files,'prepared')

def apply_registry(serial,kind,reg):
    candidate={**reg,'jobs':reg['jobs']+[check.definition() if kind=='check' else copy.definition()]}
    preview=rpc(serial,'jobs.preview',{'candidate':candidate})
    need(preview.get('base_revision')==reg['revision'] and
         preview.get('job_count')==len(candidate['jobs']) and
         preview.get('includes_destructive_sync') is False and
         isinstance(preview.get('proof'),str) and preview['proof'],
         'TARGET_REGISTRY_PREVIEW_REJECTED')
    applied=rpc(serial,'jobs.apply',{'candidate':candidate,'proof':preview['proof']})
    need(applied.get('revision')==reg['revision']+1,'TARGET_REGISTRY_APPLY_AMBIGUOUS')
    after,_=registry(serial)
    expected=check.definition() if kind=='check' else copy.definition()
    need(any(all(j.get(k)==v for k,v in expected.items()) for j in after['jobs']),
         'TARGET_REGISTRY_PERSISTENCE_FAILED')

def run(opts):
    stamp=target(opts.serial)
    reg,_=registry(opts.serial)
    checked={}
    for kind,job in (('check',check.NAME),('copy',copy.NAME)):
        if any(j.get('name')==job for j in reg['jobs']):
            checked[kind]=verify(opts.serial,kind,'prepared' if kind=='check' else opts.copy_phase)
    if opts.action=='inspect':
        print(json.dumps({'state':'PASS_TARGET_M3_FIXTURE_INSPECTION_ONLY',
                          'target_serial':opts.serial,'target_fingerprint_sha256':stamp,
                          'registry_revision':reg['revision'],'verified_fixtures':checked},sort_keys=True))
        return 0
    need(opts.apply,'EXPLICIT_--apply_REQUIRED')
    kind='check' if opts.action=='prepare-check' else 'copy'
    name=check.NAME if kind=='check' else copy.NAME
    need(not any(j.get('name')==name for j in reg['jobs']), 'TARGET_FIXTURE_DEFINITION_ALREADY_EXISTS')
    result=stage(opts.serial,kind,opts.files)
    apply_registry(opts.serial,kind,reg)
    print(json.dumps({'state':'PASS_TARGET_M3_'+kind.upper()+'_FIXTURE_PREPARED_ONLY',
                      'target_serial':opts.serial,'target_fingerprint_sha256':stamp,
                      'fixture':result,'registry_applied':True,'jobs_executed':False},sort_keys=True))
    return 0

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('inspect','prepare-check','prepare-copy'),default='inspect',nargs='?')
    p.add_argument('--serial',required=True)
    p.add_argument('--apply',action='store_true')
    p.add_argument('--files',type=int,default=None)
    p.add_argument('--copy-phase',choices=('prepared','complete'),default='prepared')
    o=p.parse_args(argv)
    if o.files is None:o.files=512 if o.action=='prepare-check' else 128
    try:return run(o)
    except (Blocked,ValueError,KeyError,OSError,TypeError) as exc:
        print(json.dumps({'state':'BLOCKED_TARGET_M3_FIXTURE','reason':str(exc)[:128]},sort_keys=True))
        return 2

if __name__=='__main__': raise SystemExit(main())
