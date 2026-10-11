#!/usr/bin/env python3
"""SB-Q03R1 evidence reconciliation; emits NO approvals, locks, signatures or gates.

Run against an externally acquired SB-Q03 evidence directory, containing inputs/
and outputs/. The recorded runner's own SHA256SUMS is NOT independent custody.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import zipfile

import source_build as build

FILES = ('inputs/magisk-rclone_arm64-v8a.zip','inputs/newfuture-release.json',
         'inputs/bclone-commit.json','outputs/skybind-upstream-raw-unattested.json')
SHA = re.compile(r'[a-f0-9]{64}\Z')
COMMIT = '7b63b1a4cc9d13465721ebbfc96f2f9bd810f600'
BC_PARENT = 'a529fad8d158723ca2ce265be47332e3538830a9'
CANDIDATE_SHA = '04ebfcc8c21c9583b7d4c723e2e69c1d3bbbd24432f6728ffbc2947e5282aa43'
ASSET_ID = 499099249
RUN_ID = 38099529777
ZIP_NAMES = {'system/vendor/bin/rclone', 'system/vendor/bin/fusermount3'}
MAX_ZIP_MEMBERS = 128
MAX_UNCOMPRESSED = 512 * 1024 * 1024

class Rejected(ValueError):
    pass


def read_json(path: Path) -> dict:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 4*1024*1024:
        raise Rejected('invalid metadata file '+str(path))
    try:
        obj=json.loads(path.read_text(encoding='utf-8'))
    except (ValueError,UnicodeError) as e:
        raise Rejected('malformed metadata JSON '+str(path)) from e
    if not isinstance(obj,dict):
        raise Rejected('JSON must be an object')
    return obj


def checked_path(root: Path, name: str) -> Path:
    p = root / name
    if (root / Path(name).parts[0]).is_symlink() or p.is_symlink() or not p.is_file() or p.resolve().parent != (root / Path(name).parent).resolve():
        raise Rejected('missing, symlinked or escaping evidence file '+name)
    return p


def reconcile(root: Path, lock_path: Path = build.DEFAULT_LOCK) -> dict:
    if root.is_symlink() or not root.is_dir():
        raise Rejected('evidence root must be a directory, not a symlink')
    root=root.resolve(strict=True)
    manifest=checked_path(root,'outputs/SHA256SUMS')
    if manifest.stat().st_size>8192:
        raise Rejected('unexpected checksum manifest size')
    entries={}
    for line in manifest.read_text(encoding='ascii').splitlines():
        m = re.fullmatch(r'([0-9a-f]{64})  (inputs/[A-Za-z0-9_.-]+|outputs/[A-Za-z0-9_.-]+)',line)
        if not m or m[2] in entries:
            raise Rejected('malformed or duplicate SHA256SUMS entry')
        entries[m[2]]=m[1]
    if set(entries)!=set(FILES):
        raise Rejected('incomplete or unexpected SHA256SUMS inventory')
    for name in FILES:
        p=checked_path(root,name)
        if p.stat().st_size > (200*1024*1024 if name.endswith('.zip') else 4*1024*1024):
            raise Rejected('evidence file too large: '+name)
        if build.filehash(p)!=entries[name]:
            raise Rejected('SHA256SUMS checksum mismatch: '+name)
    arc=checked_path(root,FILES[0])
    release=read_json(checked_path(root,FILES[1]))
    commit=read_json(checked_path(root,FILES[2]))
    raw=read_json(checked_path(root,FILES[3]))
    if entries[FILES[0]]!=CANDIDATE_SHA:
        raise Rejected('NewFuture archive changed from reviewed run')
    if release.get('tag_name')!='v1.75.0' or release.get('immutable') is not False or release.get('draft') is not False:
        raise Rejected('unexpected upstream release metadata')
    if release.get('html_url')!='https://github.com/NewFuture/rclone-fuse3-magisk/releases/tag/v1.75.0':
        raise Rejected('incorrect release origin')
    matches=[a for a in release.get('assets',[]) if isinstance(a,dict) and a.get('name')=='magisk-rclone_arm64-v8a.zip']
    if len(matches)!=1 or matches[0].get('id')!=ASSET_ID or matches[0].get('size')!=arc.stat().st_size:
        raise Rejected('release asset identity/size mismatch')
    if matches[0].get('digest')!='sha256:'+CANDIDATE_SHA:
        raise Rejected('release metadata digest differs')
    if matches[0].get('browser_download_url')!='https://github.com/NewFuture/rclone-fuse3-magisk/releases/download/v1.75.0/magisk-rclone_arm64-v8a.zip':
        raise Rejected('release URL differs')
    if commit.get('sha')!=COMMIT or commit.get('html_url')!='https://github.com/BenjiThatFoxGuy/bclone/commit/'+COMMIT:
        raise Rejected('bclone source commit identity mismatch')
    if commit.get('commit',{}).get('verification',{}).get('verified') is not False or commit['commit']['verification'].get('reason')!='unsigned':
        raise Rejected('unsigned Git commit observation differs; a new independent review is required')
    if [p.get('sha') for p in commit.get('parents',[])]!=[BC_PARENT]:
        raise Rejected('bclone parent differs')
    if raw.get('producer')!='SB-Q03-source-provenance' or raw.get('evidence_class')!='RAW_UNATTESTED':
        raise Rejected('wrong raw evidence producer/class')
    if raw.get('newfuture',{}).get('sha256_candidate')!=CANDIDATE_SHA or raw.get('bclone',{}).get('commit_candidate')!=COMMIT:
        raise Rejected('raw candidate identities differ')
    if raw.get('source_lock_altered') is not False or raw.get('gate_g01')!='BLOCKED' or raw.get('final_seal')!='NOT_ISSUED':
        raise Rejected('unexpected qualification claims')
    if raw.get('newfuture',{}).get('release_api_json_sha256')!=entries[FILES[1]] or raw.get('bclone',{}).get('github_commit_api_json_sha256')!=entries[FILES[2]]:
        raise Rejected('report API hashes differ from evidence snapshots')
    if raw.get('newfuture',{}).get('size')!=arc.stat().st_size or raw.get('newfuture',{}).get('github_asset_id')!=ASSET_ID:
        raise Rejected('raw release asset identity mismatch')
    names=set()
    with zipfile.ZipFile(arc) as z:
        infos=z.infolist()
        if len(infos)>MAX_ZIP_MEMBERS or sum(i.file_size for i in infos)>MAX_UNCOMPRESSED:
            raise Rejected('archive ZIP too large')
        for info in infos:
            path=PurePosixPath(info.filename)
            if (info.filename.startswith('/') or '\\' in info.filename or '..' in path.parts
                    or str(path) != info.filename.rstrip('/') or info.filename in names
                    or (info.external_attr >> 16 & 0o170000) == 0o120000):
                raise Rejected('ZIP traversal, duplicate or symlink')
            names.add(info.filename)
        if z.testzip() is not None:
            raise Rejected('archive ZIP CRC mismatch')
        for name in ZIP_NAMES:
            if name not in names:raise Rejected('missing Android runtime/helper '+name)
            with z.open(name) as stream:
                h=stream.read(64)
            if len(h)!=64 or h[:7]!=b'\x7fELF\x02\x01\x01' or int.from_bytes(h[18:20],'little') != 183:
                raise Rejected('runtime/helper not ELF64 AArch64')
    lock=read_json(lock_path)
    if lock.get('newfuture',{}).get('archive_sha256') is not None or any(lock.get('bclone',{}).get(k) is not None for k in ('commit','ndk_revision','go_version')):
        raise Rejected('source lock has pins; this review requires an unchanged unapproved lock')
    return {'schema_version':1,'kind':'SB_Q03R1_EVIDENCE_RECONCILIATION',
            'source':'USER_ACQUIRED_GITHUB_ACTIONS_BUNDLE', 'workflow_run_candidate':RUN_ID,
            'manifest_sha256':build.filehash(manifest),'inputs_sha256':entries,
            'reconciliation':'CONSISTENT_UNATTESTED',
            'newfuture':{'sha256_candidate':CANDIDATE_SHA,'status':'PENDING_BINARY_CUSTODY',
                         'release_immutable':False,'reported_rclone_vcs_modified':True},
            'bclone':{'commit_candidate':COMMIT,'status':'PENDING_SOURCE_REVIEW',
                      'github_signature_observation':'unsigned'},
            'toolchain':{'selected_go_for_future_builds':build.PIN_GO,
                         'selected_ndk_for_future_builds':build.PIN_NDK,
                         'acquisition_authenticated':False},
            'missing':['Authenticated NewFuture build custody/dirty-source explanation',
                       'Independent exact bclone source/dependency approval',
                       'Authenticated toolchain package digests and authorized pin sign-off',
                       'Two independent actual Android arm64 builds and device tests'],
            'trust_pins_approved':False,'may_populate_source_lock':False,
            'gates':'G01-G08_BLOCKED','final_seal':'NOT_ISSUED'}


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence-dir',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--lock',type=Path,default=build.DEFAULT_LOCK)
    a=p.parse_args()
    try:
        root=a.evidence_dir.resolve(strict=True)
        out=a.output.absolute()
        lock=a.lock.resolve(strict=True)
        repo=build.ROOT.resolve(strict=True)
        if out.is_symlink() or out.exists() or out == repo or repo in out.parents or root == out or root in out.parents:
            raise Rejected('output must be new and outside repository and evidence inputs')
        result=reconcile(root,lock)
        out.parent.mkdir(parents=True,exist_ok=True)
        fd=os.open(out,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'wb') as f:
            f.write(build.canonical(result))
    except (Rejected,OSError,ValueError,UnicodeError,zipfile.BadZipFile) as exc:
        print('SB-Q03R1 REVIEW BLOCKED: '+str(exc),file=sys.stderr)
        return 3
    print('SB-Q03R1 CONSISTENT_UNATTESTED: '+str(out))
    print('No pin approval, no gate change, no final seal')
    return 0

if __name__=='__main__':
    sys.exit(main())
