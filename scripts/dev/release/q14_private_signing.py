#!/usr/bin/env python3
"""SB-Q14R2: private Ed25519 signatures over original CI candidate subject hashes.

No GitHub attestation API, Sigstore public transparency log, CFS1 gate promotion,
or release seal. Verifier MUST use a public key anchored outside downloaded artifacts.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

PROVIDERS = ('newfuture', 'bclone')
SUBJECT_NAMES = ('candidate-evidence.json',) + tuple(f'skybind-{p}-CANDIDATE-UNQUALIFIED.zip' for p in PROVIDERS)
MANIFEST = 'candidate-provenance.json'
SIGNATURE = 'candidate-provenance.ed25519'
PUBLIC = 'candidate-signer-public.pem'
WORKFLOW = '.github/workflows/skybind-q14-attested-candidates.yml'
KIND = 'SB_Q14_PRIVATE_CI_SIGNED_MANIFEST_NOT_CFS1'
SHA40 = re.compile(r'[0-9a-f]{40}\Z')
REPO = re.compile(r'[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+\Z')


def sha(path: Path) -> str:
    d = hashlib.sha256()
    with path.open('rb') as f:
        for part in iter(lambda: f.read(1024*1024), b''):
            d.update(part)
    return d.hexdigest()


def check_file(path: Path, max_bytes: int) -> None:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > max_bytes:
        raise ValueError('INVALID_OR_OVERSIZED_FILE_' + path.name)


def call(args: list[str]):
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=40, check=False)
    if p.returncode:
        raise ValueError('OPENSSL_SIGNATURE_OPERATION_FAILED')
    return p.stdout


def statement(stage: Path, *, repo: str, head_sha: str, run_id: int, attempt: int, lane: str) -> dict:
    if not REPO.fullmatch(repo) or not SHA40.fullmatch(head_sha) or run_id < 1 or attempt < 1 or lane not in ('A','B'):
        raise ValueError('INVALID_CI_IDENTITY')
    files = {}
    for name in SUBJECT_NAMES:
        p = stage / name
        check_file(p, 450*1024*1024 if name.endswith('.zip') else 2*1024*1024)
        files[name] = sha(p)
    return {'schema_version': 1, 'kind': KIND, 'repository': repo, 'workflow': WORKFLOW,
            'git_commit': head_sha, 'run_id': run_id, 'run_attempt': attempt, 'lane': lane,
            'subjects_sha256': files, 'independent_attestation': False, 'final_seal': 'NOT_ISSUED'}


def canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=True)+'\n').encode()


def sign(stage: Path, key: Path, **ident) -> dict:
    check_file(key, 16*1024)
    manifest = statement(stage, **ident)
    for name in (MANIFEST, SIGNATURE, PUBLIC):
        if (stage/name).exists() or (stage/name).is_symlink():
            raise ValueError('SIGNING_OUTPUT_ALREADY_EXISTS')
    (stage/MANIFEST).write_bytes(canonical(manifest))
    try:
        pub = call(['openssl', 'pkey', '-in', str(key), '-pubout'])
        if b'BEGIN PUBLIC KEY' not in pub:
            raise ValueError('SIGNER_PUBLIC_KEY_INVALID')
        (stage/PUBLIC).write_bytes(pub)
        call(['openssl','pkeyutl','-sign','-rawin','-inkey',str(key),
              '-in',str(stage/MANIFEST),'-out',str(stage/SIGNATURE)])
        check_file(stage/SIGNATURE, 1024)
        verify(stage, stage/PUBLIC, **ident)
        return {'status': 'PRIVATE_CI_MANIFEST_SIGNED_NOT_CFS1', 'public_key_sha256': sha(stage/PUBLIC)}
    except BaseException:
        for name in (MANIFEST, SIGNATURE, PUBLIC):
            (stage/name).unlink(missing_ok=True)
        raise


def verify(stage: Path, trusted_public_key: Path, **ident) -> dict:
    check_file(trusted_public_key, 16*1024)
    for name in (MANIFEST, SIGNATURE, PUBLIC):
        check_file(stage/name, 2*1024*1024 if name==MANIFEST else 16*1024)
    if (stage/PUBLIC).read_bytes() != trusted_public_key.read_bytes():
        raise ValueError('PUBLIC_KEY_DOES_NOT_MATCH_TRUST_ANCHOR')
    raw = (stage/MANIFEST).read_bytes()
    data = json.loads(raw)
    if not isinstance(data, dict) or raw != canonical(data):
        raise ValueError('INVALID_CANONICAL_MANIFEST')
    expected = statement(stage, **ident)
    if data != expected:
        raise ValueError('SIGNED_MANIFEST_CI_IDENTITY_OR_SUBJECT_MISMATCH')
    call(['openssl','pkeyutl','-verify','-rawin','-pubin','-inkey',str(trusted_public_key),
          '-in',str(stage/MANIFEST),'-sigfile',str(stage/SIGNATURE)])
    return {'status': 'PRIVATE_ED25519_SIGNATURE_VERIFIED_NOT_CFS1',
            'public_key_sha256': sha(trusted_public_key), 'subjects_sha256': expected['subjects_sha256'],
            'independent_attestation': False, 'final_seal': 'NOT_ISSUED'}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action',choices=['sign','verify'])
    ap.add_argument('--stage-dir',type=Path,required=True)
    ap.add_argument('--lane',choices=['A','B'],required=True)
    ap.add_argument('--repo',required=True)
    ap.add_argument('--sha',required=True)
    ap.add_argument('--run-id',type=int,required=True)
    ap.add_argument('--run-attempt',type=int,required=True)
    ap.add_argument('--key-file',type=Path)
    ap.add_argument('--trusted-public-key',type=Path)
    ns=ap.parse_args(argv)
    try:
        if not ns.stage_dir.is_dir() or ns.stage_dir.is_symlink():
            raise ValueError('STAGE_DIR_INVALID')
        ident={'lane':ns.lane,'repo':ns.repo,'head_sha':ns.sha,'run_id':ns.run_id,'attempt':ns.run_attempt}
        if ns.action=='sign':
            if ns.key_file is None: raise ValueError('SIGNING_PRIVATE_KEY_REQUIRED')
            out=sign(ns.stage_dir,ns.key_file,**ident)
        else:
            if ns.trusted_public_key is None: raise ValueError('EXTERNALLY_TRUSTED_PUBLIC_KEY_REQUIRED')
            out=verify(ns.stage_dir,ns.trusted_public_key,**ident)
        print(json.dumps(out,sort_keys=True))
        return 0
    except (ValueError,OSError,subprocess.TimeoutExpired,json.JSONDecodeError) as e:
        print('SB-Q14R2 BLOCKED: '+str(e)[:180],file=sys.stderr)
        return 2

if __name__=='__main__':
    sys.exit(main())
