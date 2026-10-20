#!/usr/bin/env python3
"""Explicitly prepare/remove a bounded, local-media, manual-only CHECK fixture.

Never starts/cancels a job, installs modules or clears arbitrary files. Root is
used only to invoke Skybind's typed jobs.status/preview/apply endpoints; all
filesystem writes occur as the invoking Termux user inside one exact test path.
Use --apply for creation/removal; default inspect is read-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

CLI = '/data/adb/modules/skybind/system/bin/skybind'
NAME = 'M3DisposableCheck'
ROOT = Path('/storage/emulated/0/Download/.skybind-m3-disposable')
SRC, DST = ROOT/'source', ROOT/'destination'
MARKER = '.skybind-m3-disposable-v1.json'
MAX_FILES = 4096

class Blocked(Exception):
    pass


def require(test, code):
    if not test:
        raise Blocked(code)


def rpc(op, args):
    require(op in ('jobs.status', 'jobs.preview', 'jobs.apply'), 'UNREVIEWED_OPERATION')
    command = ' '.join(shlex.quote(t) for t in
                       (CLI, 'operation', op, json.dumps(args, separators=(',', ':'))))
    try:
        out = subprocess.run(['su', '-c', command], capture_output=True, text=True, timeout=35)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Blocked('SKYBIND_ROOT_CLI_UNAVAILABLE') from e
    try:
        record = json.loads(out.stdout)
    except ValueError as e:
        raise Blocked('DAEMON_RESPONSE_NON_JSON') from e
    require(out.returncode == 0 and record.get('ok') is True and
            isinstance(record.get('result'), dict), 'DAEMON_REFUSED_' + op)
    return record['result']


def registry():
    status = rpc('jobs.status', {})
    registry = status.get('registry')
    require(isinstance(registry, dict) and registry.get('schema_version') == 1
            and type(registry.get('revision')) is int and registry['revision'] >= 0,
            'REGISTRY_INVALID')
    jobs = registry.get('jobs')
    if jobs is None:  # only legacy explicit null, never silently default absent
        require('jobs' in registry, 'JOBS_MISSING')
        jobs = []
    require(isinstance(jobs, list) and all(isinstance(j, dict) for j in jobs), 'JOBS_INVALID')
    runs = status.get('runs')
    require(isinstance(runs, list), 'RUN_HISTORY_INVALID')
    return {'schema_version': 1, 'revision': registry['revision'], 'jobs': jobs}, runs


def definition():
    return {'name': NAME, 'kind': 'check', 'source': str(SRC),
            'destination': str(DST), 'enabled': True, 'interval_seconds': 0,
            'network_mode': 'offline-allowed', 'charging_only': False,
            'min_battery_percent': 0, 'next_unix': 0}


def owned(job):
    basic = definition()
    return all(job.get(key) == value for key, value in basic.items())


def reject_unsafe_registry(reg, runs):
    require(all(j.get('kind') != 'sync' for j in reg['jobs']), 'SYNC_PRESENT_REGISTRY_REFUSED')
    require(all(not (r.get('name') == NAME and r.get('state') in ('RUNNING', 'QUEUED'))
                for r in runs if isinstance(r, dict)), 'FIXTURE_RUN_ACTIVE')
    matches = [j for j in reg['jobs'] if j.get('name') == NAME]
    require(len(matches) <= 1 and all(owned(j) for j in matches), 'FIXTURE_IDENTITY_CONFLICT')
    return matches


def inspect_path(path):
    # Explicitly do not traverse test path symlinks at any level.
    for node in (ROOT, SRC, DST):
        if node.exists() or node.is_symlink():
            require(node.is_dir() and not node.is_symlink(), 'FIXTURE_SYMLINK_OR_NON_DIRECTORY')
    if path.exists() or path.is_symlink():
        require(path.is_file() and not path.is_symlink(), 'FIXTURE_UNSAFE_FILE')


def payload(i):
    # Deterministic non-secret contents and digest; bounded to 4 KiB/file.
    seed = hashlib.sha256(f'skybind-m3-disposable:{i}'.encode()).digest()
    return seed * 128


def fileset(count):
    return {f'sample-{i:05d}.bin' for i in range(count)}


def check_files():
    marker = ROOT/MARKER
    inspect_path(marker)
    require(marker.is_file(), 'FIXTURE_MARKER_MISSING')
    try:
        info = json.loads(marker.read_text())
    except (ValueError, OSError) as exc:
        raise Blocked('FIXTURE_MARKER_INVALID') from exc
    count = info.get('count')
    require(info.get('schema') == 'skybind-m3-disposable-v1' and
            type(count) is int and 64 <= count <= MAX_FILES and
            set(ROOT.iterdir()) == {SRC, DST, marker}, 'FIXTURE_MARKER_OR_MEMBERS_INVALID')
    names = fileset(count)
    for folder in (SRC, DST):
        require(folder.is_dir() and not folder.is_symlink() and
                {p.name for p in folder.iterdir()} == names, 'FIXTURE_FOREIGN_FILE_FOUND')
        for i in range(count):
            f = folder/f'sample-{i:05d}.bin'
            inspect_path(f)
            require(f.read_bytes() == payload(i), 'FIXTURE_CONTENT_MODIFIED')
    return count


def build_files(count):
    require(64 <= count <= MAX_FILES, 'FILE_COUNT_OUT_OF_BOUNDS')
    require(not ROOT.exists() and not ROOT.is_symlink(), 'FIXTURE_PATH_ALREADY_EXISTS')
    ROOT.mkdir(mode=0o700)
    SRC.mkdir(mode=0o700)
    DST.mkdir(mode=0o700)
    for i in range(count):
        data = payload(i)
        for folder in (SRC, DST):
            with (folder/f'sample-{i:05d}.bin').open('xb') as f:
                f.write(data)
    (ROOT/MARKER).write_text(json.dumps({'schema':'skybind-m3-disposable-v1',
                                          'count':count}, sort_keys=True)+'\n')
    return check_files()


def apply_registry(candidate, *, expected_revision, expected_count):
    proof = rpc('jobs.preview', {'candidate': candidate})
    require(proof.get('base_revision') == expected_revision and
            proof.get('job_count') == expected_count and
            proof.get('includes_destructive_sync') is False and
            isinstance(proof.get('proof'), str) and proof['proof'], 'PREVIEW_MISMATCH')
    applied = rpc('jobs.apply', {'candidate': candidate, 'proof': proof['proof']})
    require(applied.get('revision') == expected_revision + 1, 'APPLY_AMBIGUOUS')
    return registry()[0]


def cleanup_files():
    count = check_files()  # absolutely no recursive delete and no foreign content
    for folder in (SRC, DST):
        for i in range(count):
            (folder/f'sample-{i:05d}.bin').unlink()
        folder.rmdir()
    (ROOT/MARKER).unlink()
    ROOT.rmdir()


def run(action, apply, count):
    current, runs = registry()
    matches = reject_unsafe_registry(current, runs)
    print(json.dumps({'action': action, 'revision': current['revision'],
                      'configured_jobs': len(current['jobs']),
                      'fixture_registered': bool(matches),
                      'fixture_directory_present': ROOT.exists(),
                      'mutation_authorized': apply}, sort_keys=True))
    if action == 'inspect':
        return
    if not apply:
        print('DRY RUN ONLY; add --apply to authorize this exact fixture change')
        return
    if action == 'prepare':
        if matches:
            check_files()
            print('EXISTING_OWNED_FIXTURE_VERIFIED')
            return
        build_files(count)
        proposed = current['jobs'] + [definition()]
        after = apply_registry({**current, 'jobs': proposed},
                               expected_revision=current['revision'], expected_count=len(proposed))
        require(len([j for j in after['jobs'] if j.get('name') == NAME]) == 1,
                'FIXTURE_REGISTER_VERIFY_FAILED')
        print('PREPARED_MANUAL_ONLY_CHECK_FIXTURE')
    elif action == 'remove':
        if matches:
            # Only owned metadata may be removed; leave unrelated state untouched.
            proposed = [j for j in current['jobs'] if j.get('name') != NAME]
            after = apply_registry({**current, 'jobs': proposed},
                                   expected_revision=current['revision'], expected_count=len(proposed))
            require(not any(j.get('name') == NAME for j in after['jobs']),
                    'FIXTURE_REMOVE_VERIFY_FAILED')
        if ROOT.exists():
            cleanup_files()
        print('REMOVED_TEST_OWNED_DEFINITION_AND_VERIFIED_FILES')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('inspect','prepare','remove'), nargs='?', default='inspect')
    p.add_argument('--apply', action='store_true')
    p.add_argument('--files', type=int, default=512,
                   help='Exact disposable file pairs, 64..4096; default 512')
    opts = p.parse_args(argv)
    require(opts.action != 'inspect' or not opts.apply, 'UNEXPECTED_INSPECT_APPLY')
    run(opts.action, opts.apply, opts.files)
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except Blocked as error:
        print('BLOCKED:', error, file=sys.stderr)
        sys.exit(2)
