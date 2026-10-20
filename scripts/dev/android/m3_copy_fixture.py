#!/usr/bin/env python3
"""Opt-in, exact-path disposable COPY fixture. Never invokes job.run.

Prepare creates source files and ONE destination sentinel; it never pre-populates
copied files. Verify checks each written destination file against independently
recreated deterministic bytes, plus the protected sentinel, with SHA-256 evidence.
No recursive deletion, no symlinks, no foreign file tolerance or silent overwrite.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

from m3_disposable_fixture import rpc, Blocked, require

NAME = 'M3DisposableCopy'
ROOT = Path('/storage/emulated/0/Download/.skybind-m3-copy')
SRC, DST = ROOT/'source', ROOT/'destination'
MARKER = 'fixture-v1.json'
SENTINEL = 'preexisting.keep'
MIN_FILES, MAX_FILES = 64, 1024


def payload(i):
    return hashlib.sha256(f'skybind-m3-copy-v1:{i}'.encode()).digest() * 128


def names(count):
    return {f'copy-{i:05d}.bin' for i in range(count)}


def definition():
    return dict(name=NAME, kind='copy', source=str(SRC), destination=str(DST),
                enabled=True, interval_seconds=0, network_mode='offline-allowed',
                charging_only=False, min_battery_percent=0, next_unix=0)


def safe_path(path, *, directory=False):
    require(not path.is_symlink(), 'COPY_SYMLINK_REJECTED')
    if path.exists():
        require(path.is_dir() if directory else path.is_file(), 'COPY_PATH_TYPE_INVALID')


def fixture_state(phase):
    require(phase in ('prepared', 'complete'), 'COPY_PHASE_INVALID')
    for p in (ROOT, SRC, DST):
        safe_path(p, directory=True)
        require(p.is_dir(), 'COPY_FIXTURE_DIRECTORY_MISSING')
    safe_path(ROOT/MARKER)
    doc=json.loads((ROOT/MARKER).read_text())
    count=doc.get('count')
    require(doc.get('schema')=='skybind-m3-copy-v1' and type(count) is int and
            MIN_FILES <= count <= MAX_FILES, 'COPY_MARKER_INVALID')
    require({p.name for p in ROOT.iterdir()} == {'source','destination',MARKER},
            'COPY_FOREIGN_ROOT_ENTRY')
    expected=names(count)
    require({p.name for p in SRC.iterdir()} == expected, 'COPY_SOURCE_MEMBERSHIP_MISMATCH')
    wanted={SENTINEL} | (expected if phase=='complete' else set())
    require({p.name for p in DST.iterdir()} == wanted, 'COPY_DEST_MEMBERSHIP_MISMATCH')
    sentinel=DST/SENTINEL
    safe_path(sentinel)
    require(sentinel.read_bytes()==b'SKYBIND-M3-COPY-DO-NOT-OVERWRITE\n',
            'COPY_SENTINEL_CHANGED')
    hash_all=hashlib.sha256()
    for i in range(count):
        name=f'copy-{i:05d}.bin'
        data=payload(i)
        p=SRC/name
        safe_path(p)
        require(p.read_bytes()==data, 'COPY_SOURCE_HASH_MISMATCH')
        hash_all.update(name.encode()+b'\0'+hashlib.sha256(data).digest())
        if phase=='complete':
            q=DST/name
            safe_path(q)
            require(q.read_bytes()==data, 'COPY_DEST_HASH_MISMATCH')
    return {'schema':'skybind-m3-copy-integrity-v1','phase':phase,'count':count,
            'expected_content_sha256':hash_all.hexdigest(),
            'source_verified':True,'destination_verified':phase=='complete',
            'sentinel_preserved':True}


def registry():
    result=rpc('jobs.status', {})
    reg=result.get('registry')
    require(isinstance(reg,dict) and reg.get('schema_version')==1 and
            type(reg.get('revision')) is int and reg['revision'] >= 0,
            'COPY_REGISTRY_INVALID')
    # Installed daemon versions predating the Go empty-slice serialization fix
    # encode an *empty* registry as explicit JSON null. Match the previously
    # qualified M3 CHECK fixture: accept only explicit null, never a missing key.
    jobs=reg.get('jobs')
    if jobs is None:
        require('jobs' in reg, 'COPY_REGISTRY_JOBS_MISSING')
        jobs=[]
    require(isinstance(jobs,list), 'COPY_REGISTRY_INVALID')
    require(all(isinstance(j,dict) for j in jobs),'COPY_JOB_INVALID')
    runs=result.get('runs')
    require(isinstance(runs,list),'COPY_RUNS_INVALID')
    found=[j for j in jobs if j.get('name')==NAME]
    require(len(found)<=1 and all(all(j.get(k)==v for k,v in definition().items()) for j in found),
            'COPY_FIXTURE_IDENTITY_CONFLICT')
    require(not any(j.get('kind')=='sync' for j in jobs),'COPY_SYNC_JOB_PRESENT')
    require(not any(isinstance(r,dict) and r.get('name')==NAME and r.get('state') in ('RUNNING','QUEUED')
                    for r in runs), 'COPY_ACTIVE_RUN')
    return {'schema_version':1,'revision':reg['revision'],'jobs':jobs},bool(found)


def apply_registry(candidate):
    result=rpc('jobs.preview', {'candidate':candidate})
    require(result.get('base_revision')==candidate['revision'] and
            result.get('job_count')==len(candidate['jobs']) and
            result.get('includes_destructive_sync') is False and
            isinstance(result.get('proof'),str) and result['proof'], 'COPY_PREVIEW_INVALID')
    applied=rpc('jobs.apply', {'candidate':candidate,'proof':result['proof']})
    require(applied.get('revision')==candidate['revision']+1,'COPY_APPLY_UNVERIFIED')


def prepare(count):
    require(type(count) is int and MIN_FILES<=count<=MAX_FILES,'COPY_COUNT_INVALID')
    reg,exists=registry()
    require(not exists and not ROOT.exists() and not ROOT.is_symlink(), 'COPY_FIXTURE_ALREADY_EXISTS')
    ROOT.mkdir(mode=0o700)
    SRC.mkdir(mode=0o700)
    DST.mkdir(mode=0o700)
    for i in range(count):
        with (SRC/f'copy-{i:05d}.bin').open('xb') as f: f.write(payload(i))
    with (DST/SENTINEL).open('xb') as f: f.write(b'SKYBIND-M3-COPY-DO-NOT-OVERWRITE\n')
    with (ROOT/MARKER).open('x') as f:
        json.dump({'schema':'skybind-m3-copy-v1','count':count},f,sort_keys=True)
    fixture_state('prepared')
    apply_registry({**reg,'jobs':reg['jobs']+[definition()]})
    return fixture_state('prepared')


def remove():
    reg,exists=registry()
    if ROOT.exists():
        # Preserve anything unknown or half-transferred; no removal until complete verification.
        report=fixture_state('complete')
    else:
        require(not exists,'COPY_REGISTRY_WITHOUT_FILES')
        return {'removed':True,'empty':True}
    if exists:
        apply_registry({**reg,'jobs':[j for j in reg['jobs'] if j['name']!=NAME]})
    count=report['count']
    for i in range(count):
        (SRC/f'copy-{i:05d}.bin').unlink()
        (DST/f'copy-{i:05d}.bin').unlink()
    (DST/SENTINEL).unlink()
    SRC.rmdir();DST.rmdir();(ROOT/MARKER).unlink();ROOT.rmdir()
    return {'removed':True,'count':count}


def run(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('inspect','prepare','verify','remove'))
    p.add_argument('--apply',action='store_true')
    p.add_argument('--files',type=int,default=128)
    args=p.parse_args(argv)
    require(args.apply == (args.action in ('prepare','remove')) if args.action!='inspect' else not args.apply,
            'COPY_EXPLICIT_APPLY_REQUIRED_OR_UNEXPECTED')
    if args.action=='prepare': result=prepare(args.files)
    elif args.action=='remove': result=remove()
    else:
        reg,exists=registry()
        require(exists,'COPY_FIXTURE_NOT_REGISTERED')
        result=fixture_state('prepared' if args.action=='inspect' else 'complete')
    print(json.dumps(result,sort_keys=True))
    return 0

if __name__=='__main__':
    try: sys.exit(run())
    except (Blocked,OSError,ValueError,KeyError,TypeError,json.JSONDecodeError) as exc:
        print('BLOCKED:',str(exc)[:128],file=sys.stderr)
        sys.exit(2)
