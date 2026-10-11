#!/usr/bin/env python3
"""SB-Q03: collect reviewable, RAW/UNATTESTED upstream pin candidates.

This tool NEVER modifies source.lock.json, issues trust signatures, or grants any gate.
GitHub API snapshots are claims supplied by the caller, NOT independent attestation.
Run from a checkout with inputs acquired separately over trusted HTTPS/official Git.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import source_build as q02

NF = 'NewFuture/rclone-fuse3-magisk'
BC = 'BenjiThatFoxGuy/bclone'
TAG = 'v1.75.0'
ASSET = 'magisk-rclone_arm64-v8a.zip'
MAX_JSON = 4 * 1024 * 1024
MAX_ASSET = 512 * 1024 * 1024
COMMIT = re.compile(r'[0-9a-f]{40}\Z')
SHA = re.compile(r'[0-9a-f]{64}\Z')

class Rejected(ValueError):
    pass


def sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def load_json(p: Path) -> dict:
    if not p.is_file() or p.is_symlink() or p.stat().st_size > MAX_JSON:
        raise Rejected('metadata must be a non-symlink JSON file <=4 MiB')
    try:
        obj = json.loads(p.read_text(encoding='utf-8'))
    except (ValueError, UnicodeError) as exc:
        raise Rejected('unreadable metadata JSON') from exc
    if not isinstance(obj, dict):
        raise Rejected('expected a JSON object')
    return obj


def check_release(meta: dict, archive: Path) -> dict:
    if meta.get('tag_name') != TAG or meta.get('html_url') != f'https://github.com/{NF}/releases/tag/{TAG}':
        raise Rejected('release identity/tag differs from the official NewFuture release')
    if meta.get('draft') is not False or meta.get('prerelease') is not False:
        raise Rejected('release is draft/prerelease or metadata unavailable')
    if not isinstance(meta.get('assets'), list):
        raise Rejected('missing GitHub release assets')
    matches = [x for x in meta['assets'] if isinstance(x, dict) and x.get('name') == ASSET]
    if len(matches) != 1:
        raise Rejected('release asset missing or duplicated')
    item = matches[0]
    url = f'https://github.com/{NF}/releases/download/{TAG}/{ASSET}'
    if item.get('browser_download_url') != url:
        raise Rejected('release asset download URL is not the exact official path')
    if archive.name != ASSET or not archive.is_file() or archive.is_symlink():
        raise Rejected('NewFuture asset must be a regular file with its official filename')
    size = archive.stat().st_size
    if size <= 0 or size > MAX_ASSET or type(item.get('size')) is not int or item['size'] != size:
        raise Rejected('archive missing, oversized, or mismatched GitHub asset size')
    digest = sha_file(archive)
    declared = item.get('digest')
    if not isinstance(declared, str) or not declared.startswith('sha256:') or not SHA.fullmatch(declared[7:]):
        raise Rejected('GitHub asset API lacks a valid SHA-256 digest; no pin candidate')
    if digest != declared[7:]:
        raise Rejected('archive SHA-256 differs from GitHub release asset metadata')
    if type(item.get('id')) is not int or item['id'] <= 0:
        raise Rejected('GitHub asset ID missing')
    return {'repository': NF, 'tag': TAG, 'asset': ASSET,
            'sha256_candidate': digest, 'size': size, 'github_asset_id': item['id'],
            'release_api_json_sha256': None, 'observed_digest_matches_github_api': True}


def git(args: list[str], checkout: Path) -> str:
    cp = subprocess.run(['git', '-C', str(checkout), *args], capture_output=True,
                        text=True, timeout=30, check=False)
    if cp.returncode:
        raise Rejected('git '+args[0]+' refused checkout: '+cp.stderr[-250:])
    return cp.stdout.strip()


def check_bclone(meta: dict, checkout: Path) -> dict:
    if not checkout.is_dir() or checkout.is_symlink():
        raise Rejected('bclone checkout must be a real Git directory')
    sha = git(['rev-parse', '--verify', 'HEAD^{commit}'], checkout).lower()
    if not COMMIT.fullmatch(sha):
        raise Rejected('Git checkout does not resolve to a full SHA')
    if meta.get('sha') != sha or meta.get('html_url') != f'https://github.com/{BC}/commit/{sha}':
        raise Rejected('GitHub commit API does not match checkout HEAD/official origin')
    # Worktree and Git object identity are checked here and independently in SB-Q02.
    sym = subprocess.run(['git', '-C', str(checkout), 'symbolic-ref', '-q', 'HEAD'],
                         capture_output=True, text=True, timeout=30)
    if sym.returncode == 0:
        raise Rejected('bclone checkout must be detached')
    if sym.returncode != 1:
        raise Rejected('unable to inspect detached HEAD')
    if git(['status', '--porcelain=v1', '--untracked-files=all'], checkout):
        raise Rejected('bclone checkout has tracked/untracked modifications')
    origin = git(['remote', 'get-url', 'origin'], checkout)
    if origin.rstrip('/').removesuffix('.git') != f'https://github.com/{BC}':
        raise Rejected('bclone origin is not canonical HTTPS upstream')
    obj = git(['cat-file', '-p', 'HEAD'], checkout)
    header = obj.split('\n\n', 1)[0]
    parents = [s.split(' ', 1)[1] for s in header.splitlines() if s.startswith('parent ')]
    observed = meta.get('parents')
    if not isinstance(observed, list) or any(not isinstance(parent, dict) for parent in observed) or [parent.get('sha') for parent in observed] != parents:
        raise Rejected('Git commit parent IDs differ from official GitHub API')
    if any(not COMMIT.fullmatch(p) for p in parents):
        raise Rejected('malformed parent object')
    for filename in ('go.mod', 'go.sum'):
        if not (checkout / filename).is_file() or (checkout / filename).is_symlink():
            raise Rejected('bclone missing regular '+filename)
    gomod = (checkout / 'go.mod').read_text(encoding='utf-8')
    warnings = []
    if re.search(r'^\s*replace\s', gomod, flags=re.M):
        warnings.append('go.mod replace directives need human review')
    if re.search(r'^\s*toolchain\s', gomod, flags=re.M):
        warnings.append('go.mod toolchain directive needs human review')
    # Record the GitHub claim, never assert its verification as independent trust.
    verification = meta.get('commit', {}).get('verification', {})
    if not isinstance(verification, dict):
        verification = {}
    return {'repository': BC, 'commit_candidate': sha, 'parents': parents,
            'git_origin': origin, 'detached_clean': True,
            'go_mod_sha256': sha_file(checkout / 'go.mod'),
            'go_sum_sha256': sha_file(checkout / 'go.sum'),
            'github_commit_api_json_sha256': None,
            'github_claims_signature_verified': verification.get('verified') is True,
            'github_signature_reason': str(verification.get('reason') or 'not_provided'),
            'review_warnings': warnings}


def inspect_toolchain(ndk: Path | None) -> dict:
    cp = subprocess.run(['go', 'version'], capture_output=True, text=True, timeout=15,
                        check=False) if shutil.which('go') else None
    go = cp.stdout.strip() if cp and cp.returncode == 0 else None
    ndk_rev = None
    if ndk is not None:
        if not ndk.is_dir() or ndk.is_symlink() or not (ndk/'source.properties').is_file():
            raise Rejected('NDK path must contain a real source.properties file')
        properties = (ndk/'source.properties').read_text(encoding='utf-8')
        matches = re.findall(r'^Pkg\.Revision\s*=\s*(\S+)\s*$', properties, flags=re.M)
        if len(matches) != 1:
            raise Rejected('NDK revision missing/ambiguous in source.properties')
        ndk_rev = matches[0]
    return {'observed_go_version': go, 'observed_ndk_revision': ndk_rev,
            'q02_go_version': q02.PIN_GO, 'q02_ndk_revision': q02.PIN_NDK,
            'toolchain_pins_reviewed': False,
            'security_review_required': 'Go 1.27.2 (2026-10-08) fixes security issues; assess migration from pinned Go 1.27.1'}


def collect(archive: Path, checkout: Path, release_json: Path, commit_json: Path,
            ndk: Path | None = None, lock_path: Path = q02.DEFAULT_LOCK) -> dict:
    release = load_json(release_json)
    commit = load_json(commit_json)
    nf = check_release(release, archive)
    bc = check_bclone(commit, checkout)
    nf['release_api_json_sha256'] = sha_file(release_json)
    bc['github_commit_api_json_sha256'] = sha_file(commit_json)
    lock = load_json(lock_path)
    if lock.get('schema') != 1 or lock.get('newfuture', {}).get('repository') != NF or lock.get('bclone', {}).get('repository') != BC:
        raise Rejected('source.lock identity/schema mismatch')
    if lock['newfuture'].get('tag') != TAG or lock['newfuture'].get('asset') != ASSET:
        raise Rejected('source.lock release identity mismatch')
    cand = {'newfuture': nf['sha256_candidate'], 'bclone': bc['commit_candidate']}
    current = {'newfuture': lock['newfuture'].get('archive_sha256'),
               'bclone': lock['bclone'].get('commit')}
    discrepancies = [key for key in cand if current[key] is not None and current[key] != cand[key]]
    if discrepancies:
        raise Rejected('already reviewed source lock contradicts observed upstream: '+', '.join(discrepancies))
    return {'schema_version': 1, 'producer': 'SB-Q03-source-provenance',
            'evidence_class': 'RAW_UNATTESTED', 'qualification': 'NOT_QUALIFIED',
            'gate_g01': 'BLOCKED', 'other_gates': 'BLOCKED', 'final_seal': 'NOT_ISSUED',
            'claims_are_external_api_snapshots_not_attestations': True,
            'newfuture': nf, 'bclone': bc, 'toolchain': inspect_toolchain(ndk),
            'lock_sha256': sha_file(lock_path),
            'source_lock_pins_populated': all(v is not None for v in (
                lock['newfuture'].get('archive_sha256'),lock['bclone'].get('commit'),
                lock['bclone'].get('ndk_revision'),lock['bclone'].get('go_version'))),
            'source_lock_altered': False, 'auto_approval': False,
            'independent_signature_or_device_evidence': False,
            'review_required': ['Independently authenticate GitHub origin, release signer and binary custody',
                                'Review exact bclone Git commit, module graph and submodules',
                                'Choose vetted Go/NDK toolchain before committing source.lock.json',
                                'Run independent SB-Q02 CI lanes only after approved pins',
                                'Acquire separate signed G01 and Android device evidence']}


def write_report(output: Path, data: dict, checkout: Path, lock_path: Path) -> None:
    output = output.absolute()
    checkout = checkout.resolve()
    if checkout == output or checkout in output.parents:
        raise Rejected('cannot write report inside immutable bclone checkout')
    if output.exists() or output.is_symlink():
        raise Rejected('refusing to overwrite existing evidence or symlink')
    if not output.parent.is_dir() or output.parent.is_symlink():
        raise Rejected('create the evidence output directory explicitly')
    before = sha_file(lock_path)
    payload = q02.canonical(data)
    with tempfile.NamedTemporaryFile(mode='wb', prefix='.sb-q03-', suffix='.tmp',
                                     dir=output.parent, delete=False) as fh:
        tmp = Path(fh.name)
        os.chmod(tmp, 0o600)
        try:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    try:
        if before != sha_file(lock_path):
            raise Rejected('source lock changed during evidence generation')
        os.replace(tmp, output)
    finally:
        tmp.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    cmd = sub.add_parser('collect')
    cmd.add_argument('--newfuture-archive', type=Path, required=True)
    cmd.add_argument('--bclone-checkout', type=Path, required=True)
    cmd.add_argument('--release-json', type=Path, required=True)
    cmd.add_argument('--commit-json', type=Path, required=True)
    cmd.add_argument('--ndk', type=Path)
    cmd.add_argument('--lock', type=Path, default=q02.DEFAULT_LOCK)
    cmd.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = collect(args.newfuture_archive, args.bclone_checkout,
                         args.release_json, args.commit_json, args.ndk, args.lock)
        write_report(args.output, result, args.bclone_checkout, args.lock)
    except (Rejected, OSError, subprocess.TimeoutExpired, UnicodeError, ValueError) as exc:
        print('SB-Q03 BLOCKED/RAW_UNATTESTED: '+str(exc), file=sys.stderr)
        return 3
    print('SB-Q03 collected RAW_UNATTESTED evidence: '+str(args.output))
    print('G01 BLOCKED; no pins modified; final seal NOT_ISSUED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
