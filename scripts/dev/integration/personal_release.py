#!/usr/bin/env python3
"""Skybind PERSONAL builds: keep strong local checks without external CFS1 gates.

The embedded module qualification is unchanged (CANDIDATE_ONLY_NOT_SEALED).
This script ONLY packages a previously verified local candidate for personal use.
It neither changes CFS1 nor signs, certifies, or installs a module.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts/dev/integration'))
import local_build

NAME = re.compile(r'^skybind-(bclone|newfuture)-CANDIDATE-UNQUALIFIED\.zip$')
MAX_ZIP_BYTES = 512 * 1024 * 1024
DEFAULT_DOWNLOAD = Path('/storage/emulated/0/Download')

class PersonalError(RuntimeError):
    pass


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def run_test(go_bin: str = 'go') -> None:
    # Build path also runs the full Go/WebUI suite; expose a standalone local test.
    env = os.environ.copy()
    env.update(GOTOOLCHAIN='local', GOWORK='off', CGO_ENABLED='0')
    local_build.progress('PERSONAL test: full Go suite')
    local_build.checked_command([go_bin, 'test', '-count=1', './...'], env=env, label='Go suite', show_output=True)
    local_build.progress('PERSONAL test: go vet')
    local_build.checked_command([go_bin, 'vet', './...'], env=env, label='go vet', show_output=True)
    local_build.progress('PERSONAL test: WebUI syntax and regression')
    local_build.verify_webui()
    local_build.progress('PERSONAL TEST PASS (device qualification not included)')


def _check_parent(parent: Path) -> None:
    if parent.is_symlink() or not parent.is_dir():
        raise PersonalError('Downloads destination must be a real existing directory, not a symlink: ' + str(parent))
    if not os.access(parent, os.W_OK | os.X_OK):
        raise PersonalError('Downloads destination is not writable: ' + str(parent))


def package(candidate: Path, receipt: Path, *, provider: str,
            dest: Path = DEFAULT_DOWNLOAD, timestamp: str | None = None) -> dict:
    if provider not in ('bclone', 'newfuture'):
        raise PersonalError('unknown provider')
    if candidate.is_symlink() or not candidate.is_file() or candidate.name != f'skybind-{provider}-CANDIDATE-UNQUALIFIED.zip':
        raise PersonalError('incorrect/missing provider candidate')
    if candidate.stat().st_size < 100 or candidate.stat().st_size > MAX_ZIP_BYTES:
        raise PersonalError('candidate ZIP outside expected size limits')
    if receipt.is_symlink() or not receipt.is_file() or receipt.parent != candidate.parent:
        raise PersonalError('missing build-time candidate receipt beside candidate')
    try:
        obj = json.loads(receipt.read_bytes())
        entry = obj['candidates'][provider]
    except (KeyError, ValueError, TypeError, UnicodeError) as exc:
        raise PersonalError('invalid build receipt') from exc
    digest = sha_file(candidate)
    if (obj.get('build_kind') != 'LOCAL_DEVELOPMENT_UNQUALIFIED' or
        obj.get('final_seal') != 'NOT_ISSUED' or
        obj.get('independent_attestation') is not False or
        obj.get('physical_device_tested') is not False or
        entry.get('file') != candidate.name or entry.get('sha256') != digest or
        obj.get('q12_source_build', {}).get('candidate_sha256', {}).get(provider) != digest):
        raise PersonalError('build receipt not bound to candidate or misstates qualification')
    # Skybind's existing verifier enforces full archive inventory, deterministic ZIP,
    # hashes, provider provenance, exact ELF architecture, and module identity.
    manifest = local_build.q05.release.verify_release(candidate)
    if manifest.get('qualification') != 'CANDIDATE_ONLY_NOT_SEALED' or manifest.get('runtime_provider') != provider:
        raise PersonalError('provider/qualification disagreement inside candidate ZIP')
    _check_parent(dest)
    date = timestamp or datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    if not re.fullmatch(r'\d{8}T\d{6}Z', date):
        raise PersonalError('invalid release timestamp')
    name = f'Skybind-Personal-{provider}-{date}-{digest[:12]}'
    output = dest / name
    if output.exists() or output.is_symlink():
        raise PersonalError('personal package already exists; refusing overwrite: ' + str(output))
    # Atomic directory publication. A partial result is never presented as usable.
    stage = Path(tempfile.mkdtemp(prefix='.skybind-personal-', dir=dest))
    try:
        archive_name = f'Skybind-{provider}-PERSONAL.zip'
        archive = stage / archive_name
        shutil.copyfile(candidate, archive)
        if sha_file(archive) != digest:
            raise PersonalError('copy integrity mismatch')
        check = local_build.q05.release.verify_release(archive)
        if check.get('qualification') != 'CANDIDATE_ONLY_NOT_SEALED':
            raise PersonalError('copied candidate fails full verification')
        metadata = {
            'schema_version': 1, 'track': 'PERSONAL', 'status': 'VERIFIED_LOCAL_BUILD_FOR_PERSONAL_USE',
            'product': 'skybind', 'provider': provider, 'archive': archive_name,
            'archive_sha256': digest,
            'source_receipt_sha256': sha_file(receipt),
            'source': obj.get('q12_source_build'),
            'toolchain': obj.get('toolchain'),
            'source_receipt_assurance': 'LOCAL_SELF_REPORTED_ONLY',
            'independent_attestation': False, 'formal_cfs1_seal': 'NOT_ISSUED',
            'installed_on_device': False,
            'original_archive_qualification': 'CANDIDATE_ONLY_NOT_SEALED',
        }
        (stage / 'PERSONAL_BUILD.json').write_text(json.dumps(metadata, sort_keys=True, indent=2)+'\n')
        (stage / 'SHA256SUMS').write_text(f'{digest}  {archive_name}\n')
        (stage / 'README.txt').write_text(
            'Skybind PERSONAL build for KernelSU.\n'
            'Install the Skybind-*-PERSONAL.zip file using your root manager.\n'
            'No formal CFS1 release attestation is implied or issued.\n'
            'Check SHA256SUMS if copying the ZIP to another device.\n'
            'Installing a module may restart mounts; back up configuration first.\n'
        )
        os.rename(stage, output)  # unique target; no collisions / replacement
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return {'status': 'PERSONAL_BUILD_READY', 'zip': str(output / archive_name),
            'sha256': digest, 'manifest': str(output / 'PERSONAL_BUILD.json'),
            'provider': provider, 'formal_cfs1_seal': 'NOT_ISSUED'}


def personal_build(provider: str = 'bclone', dest: Path = DEFAULT_DOWNLOAD) -> dict:
    _check_parent(dest)
    # Local build already runs the full Go suite, WebUI syntax/regressions,
    # verifies pinned Q04 inputs and validates the ARM64 output and ZIP.
    env = os.environ.copy()
    env.update(GOTOOLCHAIN='local', GOWORK='off', CGO_ENABLED='0')
    local_build.progress('PERSONAL release: go vet before building')
    local_build.checked_command([os.environ.get('SKYBIND_LOCAL_GO_BIN', 'go'), 'vet', './...'], env=env, label='go vet', show_output=True)
    report = local_build.build(provider=provider, go_bin=os.environ.get('SKYBIND_LOCAL_GO_BIN', 'go'))
    folder = Path(report['local_output'])
    return package(folder / report['candidates'][provider]['file'], folder / 'candidate-evidence.json',
                   provider=provider, dest=dest)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='cmd', required=True)
    t = sub.add_parser('test'); t.add_argument('--go-bin', default=os.environ.get('SKYBIND_LOCAL_GO_BIN', 'go'))
    b = sub.add_parser('build'); b.add_argument('--provider', choices=['bclone','newfuture'], default='bclone')
    b.add_argument('--downloads', type=Path, default=DEFAULT_DOWNLOAD)
    args = p.parse_args()
    try:
        if args.cmd == 'test':
            run_test(args.go_bin)
        else:
            print(json.dumps(personal_build(args.provider, args.downloads), sort_keys=True), flush=True)
        return 0
    except (PersonalError, local_build.LocalBuildError, local_build.q05.Rejected,
            local_build.q05.release.Reject, OSError, TypeError, ValueError, KeyError) as exc:
        print('SKYBIND_PERSONAL_BLOCKED: ' + str(exc), file=sys.stderr, flush=True)
        return 3

if __name__ == '__main__':
    sys.exit(main())
