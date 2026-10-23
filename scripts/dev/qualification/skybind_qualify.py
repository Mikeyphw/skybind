#!/usr/bin/env python3
"""Read-only upstream/device gate triage. Never sign, generate or promote evidence.

A source-only assessment cannot establish that a provider is official, that a
physical Android app can access FUSE, or that an independent reviewer signed a
release. All outputs explicitly say RAW_UNATTESTED.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))
import skybind_runtime as runtime

ROOT = Path(__file__).resolve().parents[3]
MAX_ARCHIVE = 512 * 1024 * 1024
MAX_ENTRIES = 8192
PASS = ('SOURCE_BUILD_PASS','SOURCE_CONTROL_PASS','HOST_LIFECYCLE_PASS',
        'ANDROID_SOURCE_PASS','BACKEND_FEATURE_PASS','TRANSPORT_SECURITY_PASS',
        'WEBUI_PARITY_PASS','DEVICE_RELEASE_READY')


def digest_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def run(argv: list[str], *, cwd: Path | None = None) -> str | None:
    try:
        p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout.strip() if p.returncode == 0 else None


def actual_status(root: Path = ROOT) -> dict:
    """Canonical personal release status; historical raw inspections remain below."""
    sys.path.insert(0,str(root/'scripts/dev/qualification'))
    import personal_policy
    doc=personal_policy.assess(root)
    return {'schema_version':1,'product':'skybind','kind':'PERSONAL_RELEASE_STATUS',
            'source_commit':doc['source_commit'],
            'gate_statuses':{k:v['status'] for k,v in doc['gate_checks'].items()},
            'final_status':doc['status'],
            'personal_release_policy':doc['policy'],
            'owner_approval':doc['owner_approval'],
            'personal_scope_only':True,
            'reasons':doc['reasons']}


def verify_zip_structure(path: Path, tag: str = "") -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError('archive missing or symlink')
    if path.stat().st_size <= 0 or path.stat().st_size > MAX_ARCHIVE:
        raise ValueError('archive size outside safety limits')
    with zipfile.ZipFile(path) as archive:
        members=archive.infolist()
        if len(members)>MAX_ENTRIES:
            raise ValueError('too many ZIP entries')
        seen=set()
        candidates={'rclone':0, 'fusermount3':0}
        helpers=0
        actual_files=set()
        for info in members:
            name=info.filename
            if (not name or name.startswith('/') or '\\' in name or
                any(x in ('.', '..', '') for x in name.rstrip('/').split('/'))):
                raise ValueError('unsafe ZIP member')
            if name in seen:
                raise ValueError('duplicate ZIP member')
            seen.add(name)
            if info.flag_bits & 1:
                raise ValueError('encrypted ZIP member')
            mode=(info.external_attr >> 16) & 0xffff
            if stat.S_IFMT(mode) not in (0, stat.S_IFDIR if info.is_dir() else stat.S_IFREG):
                raise ValueError('symlink/special ZIP member')
            if info.file_size > MAX_ARCHIVE:
                raise ValueError('oversized ZIP entry')
            if not info.is_dir():
                actual_files.add(name)
                base = name.rsplit('/', 1)[-1]
                if base in candidates: candidates[base] += 1
                if base.startswith('libfuse') and '.so' in base: helpers+=1
        if candidates != {'rclone':1, 'fusermount3':1}:
            raise ValueError('NewFuture binary inventory incomplete: '+str(candidates))
        try:
            mode=runtime.fuse_delivery_mode(actual_files,tag)
        except runtime.Reject as exc:
            raise ValueError('NewFuture FUSE inventory rejected: '+str(exc)) from exc
    return {'member_count':len(members),'rclone_count':1,'fusermount3_count':1,
            'libfuse_member_count':helpers,'fuse_delivery':mode,
            'static_linkage_verified':'NO_NEEDS_ELF_AND_DEVICE_QUALIFICATION' if not helpers else 'NOT_APPLICABLE'}


def inspect_newfuture(path: Path, root: Path = ROOT) -> dict:
    lock=json.loads((root/'scripts/dev/runtime/source.lock.json').read_text())['newfuture']
    if path.name != lock['asset']:
        raise ValueError('filename does not match reviewed source lock asset')
    inv=verify_zip_structure(path, lock['tag'])
    digest=digest_file(path)
    pin=lock.get('archive_sha256')
    return {'schema_version':1,'kind':'NEWFUTURE_CANDIDATE_INSPECTION',
            'repository':lock['repository'],'tag':lock['tag'],'filename':path.name,
            'sha256':digest,'inventory':inv,
            'pin_matches':bool(isinstance(pin,str) and re.fullmatch('[0-9a-f]{64}',pin) and pin==digest),
            'source_authenticity':'UNVERIFIED_BY_LOCAL_INSPECTION',
            'qualification':'RAW_UNATTESTED',
            'required_next':'Independently verify exact release asset provenance and SHA-256, then separately review/pin source.lock.json; run TWO independent reproducible builds for G01. This output alone never qualifies G01.'}


def inspect_bclone(path: Path, root: Path = ROOT) -> dict:
    if not path.is_dir() or path.is_symlink():
        raise ValueError('bclone source directory missing or symlink')
    head=run(['git','rev-parse','HEAD'],cwd=path)
    if not head or not re.fullmatch('[0-9a-f]{40,64}',head):
        raise ValueError('not a valid Git source checkout')
    dirty=run(['git','status','--porcelain'],cwd=path)
    lock=json.loads((root/'scripts/dev/runtime/source.lock.json').read_text())['bclone']
    return {'schema_version':1, 'kind':'BCLONE_CHECKOUT_INSPECTION',
            'head':head, 'checkout_clean':dirty=='',
            'lock_commit_matches':lock.get('commit')==head,
            'go_version':run(['go','version']),
            'ndk_revision':lock.get('ndk_revision'),
            'repository':lock.get('repository'),
            'source_authenticity':'UNVERIFIED_BY_LOCAL_INSPECTION',
            'qualification':'RAW_UNATTESTED',
            'required_next':'Independently authenticate bclone Git commit, Go toolchain and Android NDK; set reviewed immutable pins and perform TWO independent reproducible Android builds.'}


def safe_write_external(record: dict, path: Path, root: Path = ROOT) -> None:
    # No evidence is persisted under the repository or overwritten/symlink-followed.
    parent=path.parent.resolve(strict=True)
    if parent==root.resolve() or parent.is_relative_to(root.resolve()):
        raise ValueError('out-of-repository output path required')
    if path.is_symlink():
        raise ValueError('symlink output refused')
    data=(json.dumps(record,indent=2,sort_keys=True)+'\n').encode()
    fd=os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
    with os.fdopen(fd,'wb') as fp:
        fp.write(data);fp.flush();os.fsync(fp.fileno())


def main(argv: list[str] | None = None, *, root: Path = ROOT) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    status=sub.add_parser('status', help='evaluate canonical G01–G08 and final seal without promoting')
    nf=sub.add_parser('inspect-newfuture',help='inspect already-downloaded official candidate; never auto-pin')
    nf.add_argument('archive',type=Path)
    bc=sub.add_parser('inspect-bclone',help='inspect already-cloned source; never auto-pin')
    bc.add_argument('checkout',type=Path)
    for cmd in (status,nf,bc):
        cmd.add_argument('--output',type=Path,help='create raw 0600 JSON outside the repository (no overwrite)')
    args=parser.parse_args(argv)
    try:
        record=(actual_status(root) if args.action=='status' else
                inspect_newfuture(args.archive,root) if args.action=='inspect-newfuture' else
                inspect_bclone(args.checkout,root))
        if args.output: safe_write_external(record,args.output,root)
        print(json.dumps(record,indent=2,sort_keys=True))
        return 0 # A successful triage run is NOT a successful gate.
    except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile) as exc:
        print('SKYBIND_QUALIFICATION_INPUT_REJECTED: '+str(exc),file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())
