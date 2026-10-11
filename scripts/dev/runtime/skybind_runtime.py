#!/usr/bin/env python3
"""Offline, build-time-only Skybind runtime assembly. Never runs on-device.

Trust inputs are pinned in versioned source.lock.json. No PATH fallback,
implicit download, latest-version lookup or dynamic installed runtime state.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[3]
LOCK = ROOT / 'scripts/dev/runtime/source.lock.json'
NEWFUTURE = 'NewFuture/rclone-fuse3-magisk'
BCLONE = 'BenjiThatFoxGuy/bclone'
MAX_ARCHIVE = 512 * 1024 * 1024
MAX_MEMBER = 256 * 1024 * 1024
MAX_TOTAL = 384 * 1024 * 1024
SHA = re.compile(r'^[0-9a-f]{64}$')
COMMIT = re.compile(r'^[0-9a-f]{40}$')
REQUIRED = ('system/bin/rclone', 'system/vendor/bin/fusermount3')
# Reviewed against NewFuture v1.75.0 build.sh and scripts/build-libfuse3.sh:
# fusermount3 is built with Meson --default-library=static and the resulting
# package copies only the rclone and fusermount3 executables. Absence of a
# libfuse*.so is expected for this exact tag/layout, not evidence of a bad ZIP.
STATIC_FUSE_TAGS = frozenset({'v1.75.0'})
UPSTREAM_STATIC_PATHS = frozenset({'system/vendor/bin/rclone',
                                  'system/vendor/bin/fusermount3'})


def fuse_delivery_mode(file_names, tag: str) -> str:
    """Classify only reviewed NewFuture layouts; do not assume static for arbitrary archives."""
    files = set(file_names)
    libs = [p for p in files if PurePosixPath(p).name.startswith('libfuse')
            and '.so' in PurePosixPath(p).name]
    if libs:
        if len(libs) > 64:
            raise Reject('too many shared libfuse libraries')
        return 'shared_libfuse'
    if tag in STATIC_FUSE_TAGS and UPSTREAM_STATIC_PATHS <= files:
        return 'reviewed_static_helper_layout'
    raise Reject('no shared libfuse and no reviewed static helper layout for pinned tag')


class Reject(ValueError): pass

def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def filehash(p: Path) -> str:
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):h.update(chunk)
    return h.hexdigest()

def lock_load(p: Path = LOCK) -> dict:
    o=json.loads(p.read_text())
    if o.get('schema') != 1 or o['newfuture'].get('repository') != NEWFUTURE or o['bclone'].get('repository') != BCLONE:
        raise Reject('unexpected provider lock schema/identity')
    return o

def is_arm64_elf(blob: bytes, *, shared: bool = False) -> bool:
    if len(blob) < 64 or blob[:4] != b'\x7fELF' or blob[4] != 2 or blob[5] != 1 or blob[6] != 1:
        return False
    typ,machine = struct.unpack_from('<HH',blob,16)
    return machine == 183 and typ in ((3,) if shared else (2,3))

def check_member(z: zipfile.ZipFile, info: zipfile.ZipInfo) -> tuple[str, bytes]:
    name=info.filename
    p=PurePosixPath(name)
    if not name or name.startswith('/') or '\\' in name or any(x in ('.','..','') for x in name.split('/')):
        raise Reject('unsafe archive name: '+name)
    if info.flag_bits & 1: raise Reject('encrypted archive member')
    mode=(info.external_attr >> 16) & 0xffff
    ftype=stat.S_IFMT(mode)
    if ftype not in (0,stat.S_IFREG):raise Reject('link/special archive member: '+name)
    if info.file_size <= 0 or info.file_size > MAX_MEMBER: raise Reject('invalid member size: '+name)
    if info.compress_size > 0 and info.file_size > info.compress_size * 2000:raise Reject('archive compression bomb')
    with z.open(info) as f:
        raw=f.read(MAX_MEMBER+1)
    if len(raw)!=info.file_size:raise Reject('member length mismatch: '+name)
    return p.as_posix(),raw

def extract_newfuture(archive: Path, expected_sha: str, tag: str = '') -> dict[str, bytes]:
    if not SHA.fullmatch(expected_sha or ''):raise Reject('NewFuture SHA256 pin is absent or invalid')
    if not archive.is_file() or archive.stat().st_size > MAX_ARCHIVE:raise Reject('NewFuture archive missing/oversized')
    if filehash(archive)!=expected_sha:raise Reject('NewFuture archive checksum mismatch')
    extracted={}
    with zipfile.ZipFile(archive) as z:
        seen=set(); matches={'rclone':[],'fusermount3':[]}; libs=[]; total=0
        for info in z.infolist():
            if info.is_dir(): continue
            path=PurePosixPath(info.filename)
            if str(path) in seen:raise Reject('duplicate zip entry '+str(path))
            seen.add(str(path))
            name=path.name
            if name in matches:matches[name].append(info)
            if name.startswith('libfuse') and '.so' in name:libs.append(info)
            # Inspect and reject every archive entry's traversal/symlink type even if unused.
            if info.filename.startswith('/') or '..' in info.filename.split('/') or '\\' in info.filename:raise Reject('unsafe archive entry')
            if stat.S_IFMT((info.external_attr>>16)&0xffff) not in (0,stat.S_IFREG):raise Reject('link/special entry')
        if len(matches['rclone']) != 1 or len(matches['fusermount3']) != 1:raise Reject('ambiguous/missing rclone or fusermount3')
        mode=fuse_delivery_mode(seen, tag)
        for name, items in matches.items():
            _,data=check_member(z, items[0]);total+=len(data)
            target='system/bin/rclone' if name=='rclone' else 'system/vendor/bin/fusermount3'
            if not is_arm64_elf(data):raise Reject('non-ARM64 ELF '+name)
            extracted[target]=data
        for info in libs:
            source,data=check_member(z,info);total+=len(data)
            if total>MAX_TOTAL:raise Reject('FUSE payload exceeds budget')
            if not is_arm64_elf(data,shared=True):raise Reject('non-ARM64 libfuse')
            orig=PurePosixPath(source)
            if 'lib64' not in orig.parts:raise Reject('libfuse outside 64-bit library directory')
            target='system/vendor/lib64/'+orig.name
            if target in extracted:raise Reject('duplicate fuse library name')
            extracted[target]=data
    return extracted

def subprocess_safe(cmd:list[str],cwd:Path|None=None,env:dict|None=None)->str:
    p=subprocess.run(cmd,cwd=cwd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=1800)
    if p.returncode:raise Reject('build command failed: '+str(cmd[:2])+' '+(p.stderr or '')[-1200:])
    return p.stdout.strip()

def build_bclone(checkout:Path,commit:str,ndk:Path,ndk_revision:str,go_version:str,
                 lock_path:Path=LOCK)->bytes:
    """SB-Q02: one builder authority, never the old ambient-cache API24 path."""
    lock=lock_load(lock_path)
    if (lock['bclone'].get('commit'),lock['bclone'].get('ndk_revision'),
        lock['bclone'].get('go_version')) != (commit,ndk_revision,go_version):
        raise Reject('bclone pinned argument mismatch')
    with tempfile.TemporaryDirectory(prefix='skybind-q02-package-') as temp:
        output=Path(temp)/'source-build'
        command=[sys.executable,str(ROOT/'scripts/dev/runtime/source_build.py'),'build',
                 '--source-dir',str(checkout),'--ndk',str(ndk),'--output-dir',str(output),
                 '--lock',str(lock_path)]
        try:
            subprocess_safe(command)
        except Reject as exc:
            raise Reject('SB-Q02 immutable bclone builder rejected input: '+str(exc)) from exc
        return (output/'rclone').read_bytes()

def provenance(provider:str,payload:dict[str,bytes],lock:dict, archive_sha:str) -> dict:
    return {
      'schema_version':1,'product':'Skybind','provider':provider,'arch':'arm64',
      'engine_path':'system/bin/rclone','helper_path':'system/vendor/bin/fusermount3',
      'newfuture':{'repository':NEWFUTURE,'tag':lock['newfuture']['tag'],'archive_sha256':archive_sha},
      'bclone':({'repository':BCLONE,'commit':lock['bclone']['commit'],'ndk_revision':lock['bclone']['ndk_revision'],'go_version':lock['bclone']['go_version']} if provider=='bclone' else None),
      'fuse_delivery':('shared_libfuse' if any(PurePosixPath(n).name.startswith('libfuse') for n in payload) else 'reviewed_static_helper_layout'),
      'files':{name:{'sha256':digest(data),'size':len(data)} for name,data in sorted(payload.items())},
    }

def canonical(obj)->bytes:
    return (json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=True)+'\n').encode()

def assemble(provider:str,archive:Path,out:Path,bclone_source:Path|None=None,ndk:Path|None=None,lock_path:Path=LOCK)->bytes:
    lock=lock_load(lock_path)
    if provider not in ('newfuture','bclone'):raise Reject('unknown build-time provider')
    src=lock['newfuture']; expected=src['archive_sha256']
    if not SHA.fullmatch(expected or ''):raise Reject('NewFuture archive pin must be filled and reviewed')
    if not src['tag'] or not re.fullmatch(r'v\d+\.\d+\.\d+',src['tag']):raise Reject('NewFuture release tag must be immutable and explicit')
    if archive.name != src['asset']:raise Reject('NewFuture archive name does not match pinned asset')
    files=extract_newfuture(archive,expected,src['tag'])
    if provider=='bclone':
        if bclone_source is None or ndk is None:raise Reject('bclone source and NDK required')
        b=lock['bclone']
        files['system/bin/rclone']=build_bclone(bclone_source,b['commit'],ndk,b['ndk_revision'],b['go_version'],lock_path)
    pro=provenance(provider,files,lock,expected)
    files['runtime.provenance.json']=canonical(pro)
    files['module.prop']=(f'id=skybind\nname=Skybind\nversion=0.0.0-dev\nversionCode=1\nauthor=Skybind\ndescription=Skybind build-time {provider} runtime fixture; not an installable full application\n').encode()
    files['SHA256SUMS']=''.join(f'{digest(data)}  {name}\n' for name,data in sorted(files.items())).encode()
    # Deterministic file entries, no host filesystem metadata or ZIP symlinks.
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix='.skybind-',suffix='.zip',dir=out.parent,delete=False) as f:
        temp=Path(f.name)
    try:
        with zipfile.ZipFile(temp,'w',compression=zipfile.ZIP_STORED) as z:
            for name,data in sorted(files.items()):
                info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0))
                info.create_system=3
                info.external_attr=((0o100755 if name in REQUIRED else 0o100644)<<16)
                info.compress_type=zipfile.ZIP_STORED
                z.writestr(info,data)
        verify_package(temp)
        os.replace(temp,out)
    finally:
        temp.unlink(missing_ok=True)
    return out.read_bytes()

def verify_package(archive:Path)->dict:
    with zipfile.ZipFile(archive) as z:
        names=z.namelist()
        if names!=sorted(set(names)) or any(n.startswith('/') or '..' in n.split('/') for n in names):raise Reject('duplicate/unsafe/non-deterministic output inventory')
        if names.count('system/bin/rclone')!=1 or names.count('system/vendor/bin/fusermount3')!=1:raise Reject('runtime/helper missing or duplicated')
        pr=json.loads(z.read('runtime.provenance.json'))
        if pr.get('schema_version')!=1 or pr.get('product')!='Skybind' or pr.get('provider') not in ('newfuture','bclone'):raise Reject('invalid provenance identity')
        if set(pr['files']) != set(names)-{'runtime.provenance.json','module.prop','SHA256SUMS'}:raise Reject('provenance inventory mismatch')
        libs=[n for n in pr['files'] if PurePosixPath(n).name.startswith('libfuse') and '.so' in PurePosixPath(n).name]
        expected_delivery='shared_libfuse' if libs else 'reviewed_static_helper_layout'
        if pr.get('fuse_delivery') != expected_delivery:raise Reject('provenance FUSE delivery mismatch')
        if not libs and pr['newfuture'].get('tag') not in STATIC_FUSE_TAGS:
            raise Reject('unreviewed shared-library-free FUSE helper')
        for name,info in pr['files'].items():
            blob=z.read(name)
            if digest(blob)!=info['sha256'] or len(blob)!=info['size']:raise Reject('tampered package member: '+name)
        if not is_arm64_elf(z.read(REQUIRED[0])) or not is_arm64_elf(z.read(REQUIRED[1])):raise Reject('invalid installed ELF')
        sums=z.read('SHA256SUMS').decode().splitlines()
        expected=[f'{digest(z.read(name))}  {name}' for name in names if name!='SHA256SUMS']
        if sorted(sums)!=sorted(expected):raise Reject('SHA256SUMS mismatch')
        for zi in z.infolist():
            if zi.date_time != (1980,1,1,0,0,0):raise Reject('nondeterministic timestamps')
            mode=(zi.external_attr>>16)&0xffff
            if stat.S_IFMT(mode)!=stat.S_IFREG or stat.S_IMODE(mode)!=(0o755 if zi.filename in REQUIRED else 0o644):raise Reject('noncanonical package modes')
        return pr

def main()->int:
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest='cmd',required=True)
    a=sub.add_parser('package');a.add_argument('--provider',choices=['newfuture','bclone'],required=True);a.add_argument('--newfuture-archive',type=Path,required=True);a.add_argument('--output',type=Path,required=True);a.add_argument('--bclone-checkout',type=Path);a.add_argument('--ndk',type=Path);a.add_argument('--lock',type=Path,default=LOCK)
    b=sub.add_parser('verify');b.add_argument('archive',type=Path)
    args=p.parse_args()
    try:
        if args.cmd=='package':
            assemble(args.provider,args.newfuture_archive,args.output,args.bclone_checkout,args.ndk,args.lock)
            print('PACKAGED source-input verified: '+str(args.output))
        else:
            print(json.dumps(verify_package(args.archive),sort_keys=True))
        return 0
    except (Reject, OSError, zipfile.BadZipFile, KeyError, TypeError, subprocess.TimeoutExpired) as e:
        print('Skybind runtime input rejected: '+str(e),file=sys.stderr)
        return 1
if __name__=='__main__':sys.exit(main())
