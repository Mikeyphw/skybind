#!/usr/bin/env python3
"""Download and stage exact hosted personal APK pair, optionally upgrade in place.

Default is READ-ONLY. --install is explicit and never uninstalls/data-clears/downgrades.
Signing trust is the existing locally pinned signer, not the downloaded JSON.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from personal_apk import (APP, TEST, APP_FILE, TEST_FILE, MANIFEST_FILE, ARTIFACT,
                          HEX, SHA, CandidateError, demand, verify_manifest, file_record,
                          package_identity, apk_manifest, REPO)

SERIAL = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,90}\Z')
PATH = re.compile(r'/(?:data/app|mnt/expand)/[A-Za-z0-9_./+~\-=]+/base\.apk\Z')

def process(args, timeout=120):
    try:
        done = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CandidateError('TRANSPORT_EXECUTION_FAILED') from exc
    demand(done.returncode == 0, 'TRANSPORT_COMMAND_FAILED')
    return done.stdout

def pin_from_owner(flag):
    location = Path.home() / '.local/share/skybind/signing/signer-sha256.txt'
    if flag:
        pin = flag.strip()
    else:
        demand(location.is_file() and not location.is_symlink() and
               location.stat().st_size <= 128, 'LOCAL_SIGNER_PIN_NOT_AVAILABLE')
        pin = location.read_text().strip()
    demand(HEX.fullmatch(pin) is not None, 'INVALID_LOCAL_TRUSTED_SIGNER_PIN')
    return pin

def verify_folder(folder: Path, *, sha: str | None, run_id: int | None, pin: str):
    demand(folder.is_dir() and not folder.is_symlink(), 'ARTIFACT_FOLDER_INVALID')
    manifest_path = folder / MANIFEST_FILE
    demand(manifest_path.is_file() and not manifest_path.is_symlink() and
           manifest_path.stat().st_size < 20000, 'ARTIFACT_MANIFEST_UNAVAILABLE')
    obj = json.loads(manifest_path.read_text())
    return obj, verify_manifest(obj, folder / APP_FILE, folder / TEST_FILE,
                                expected_sha=sha, expected_run=run_id,
                                expected_pin=pin)

def gh_info(run):
    raw = process(['gh', 'run', 'view', str(run), '--repo', REPO, '--json',
                   'headSha,conclusion,event,workflowName,headBranch,status'], timeout=60)
    doc = json.loads(raw)
    demand(doc.get('conclusion') == 'success' and doc.get('status') == 'completed' and
           doc.get('workflowName') == 'Skybind Personal APK (candidate only)' and
           doc.get('event') == 'workflow_dispatch' and doc.get('headBranch') == 'main' and
           SHA.fullmatch(str(doc.get('headSha', ''))) is not None, 'HOSTED_RUN_UNTRUSTED_OR_INCOMPLETE')
    return doc['headSha']

def download(run: int, out_dir: Path, pin: str):
    sha = gh_info(run)
    demand(not out_dir.exists() and not out_dir.is_symlink(), 'DESTINATION_ALREADY_EXISTS')
    with tempfile.TemporaryDirectory(prefix='skybind-personal-fetch-') as tmp:
        staged = Path(tmp)
        process(['gh','run','download',str(run),'--repo',REPO,
                 '--name',ARTIFACT,'--dir',str(staged)], timeout=180)
        obj, receipt = verify_folder(staged, sha=sha, run_id=run, pin=pin)
        # Only known files leave the disposable downloaded directory.
        out_dir.mkdir(parents=True, mode=0o700)
        try:
            for name in (MANIFEST_FILE, APP_FILE, TEST_FILE):
                shutil.copyfile(staged/name, out_dir/name)
                (out_dir/name).chmod(0o600)
            verify_folder(out_dir, sha=sha, run_id=run, pin=pin)
        except Exception:
            shutil.rmtree(out_dir)
            raise
    return {'status': 'PERSONAL_APK_STAGED_UNQUALIFIED', 'folder': str(out_dir), **receipt}

def adb(serial, *argv, timeout=90):
    return process(['adb', '-s', serial, *argv], timeout=timeout)

def pm_path(serial, pkg):
    demand(pkg in (APP, TEST), 'PACKAGE_SELECTOR_INVALID')
    output = adb(serial, 'shell', 'pm', 'path', pkg)
    if output.strip() == '':
        return None
    lines = output.strip().splitlines()
    demand(len(lines) == 1 and lines[0].startswith('package:'), 'SPLIT_OR_UNKNOWN_PACKAGE_LAYOUT')
    path = lines[0][len('package:'):].strip()
    demand(PATH.fullmatch(path) is not None and '..' not in path, 'INSTALLED_PACKAGE_PATH_UNSAFE')
    return path

def pull_record(serial, pkg, temp_dir: Path):
    path = pm_path(serial, pkg)
    if path is None:
        return None
    out = temp_dir / (APP_FILE if pkg == APP else TEST_FILE)
    adb(serial, 'pull', path, str(out), timeout=180)
    info = file_record(out)
    demand(info['package'] == pkg, 'PULLED_PACKAGE_IDENTITY_INVALID')
    return info

def inspect_installed(serial: str, candidate: dict, trusted_pin: str):
    with tempfile.TemporaryDirectory(prefix='skybind-installed-') as tmp:
        app = pull_record(serial, APP, Path(tmp))
        test = pull_record(serial, TEST, Path(tmp))
    demand((app is None) == (test is None), 'PARTIAL_INSTALLED_APP_TEST_PAIR')
    if app is None:
        return {'state': 'ABSENT', 'old_version': None}
    demand(app['certificate_sha256'] == trusted_pin and
           test['certificate_sha256'] == trusted_pin, 'INSTALLED_SIGNER_MISMATCH')
    new_app, new_test = candidate['app'], candidate['test_apk']
    if app['sha256'] == new_app['sha256'] and test['sha256'] == new_test['sha256']:
        return {'state': 'ALREADY_INSTALLED_IDENTICAL_PAIR', 'old_version': app['version_code']}
    demand(app['version_code'] < new_app['version_code'], 'DOWNGRADE_OR_SAME_VERSION_REPLACEMENT_REFUSED')
    return {'state': 'SAME_SIGNER_HIGHER_VERSION_UPGRADE', 'old_version': app['version_code']}

def device_action(folder: Path, serial: str, pin: str, *, do_install: bool, sha: str | None):
    obj, verified = verify_folder(folder, sha=sha, run_id=None, pin=pin)
    state = inspect_installed(serial, obj, pin)
    receipt = {'status': 'PERSONAL_APK_DEVICE_PREFLIGHT_ONLY', 'serial': serial,
               'candidate_source_sha': obj['source_sha'], 'candidate_version': obj['requested_version_code'],
               'candidate_apk_sha256': obj['app']['sha256'], 'signer': pin,
               'installed_before': state, 'installer_invoked': False,
               'device_qualified': False, 'release_qualified': False}
    if not do_install:
        return receipt
    demand(state['state'] in ('ABSENT', 'SAME_SIGNER_HIGHER_VERSION_UPGRADE'),
           'INSTALL_REQUIRES_ABSENT_OR_STRICTLY_NEWER_PAIR')
    # No uninstall, --downgrade, app-data removal, root shell, or force-stop.
    try:
        adb(serial, 'install', '-r', str(folder/APP_FILE), timeout=180)
        adb(serial, 'install', '-r', '-t', str(folder/TEST_FILE), timeout=180)
        final_state = inspect_installed(serial, obj, pin)
        demand(final_state['state'] == 'ALREADY_INSTALLED_IDENTICAL_PAIR', 'POST_INSTALL_PAIR_MISMATCH')
    except (CandidateError, OSError) as exc:
        # Package installer cannot atomically upgrade TWO separately installed APKs.
        raise CandidateError('INSTALL_OR_POSTCHECK_FAILED_INSPECT_PARTIAL_PAIR') from exc
    receipt['installer_invoked'] = True
    receipt['installed_after'] = final_state
    receipt['status'] = 'PERSONAL_APK_INSTALLED_UNQUALIFIED'
    return receipt

def save_receipt(result):
    location = Path.home() / '.local/state/skybind/personal-apk'
    demand(not location.is_symlink(), 'STATE_DIRECTORY_SYMLINK')
    location.mkdir(parents=True, exist_ok=True, mode=0o700)
    name = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-receipt.json'
    path = location / name
    with path.open('x') as out:
        json.dump(result, out, sort_keys=True, indent=2)
        out.write('\n')
    path.chmod(0o600)
    return str(path)

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='action', required=True)
    fetch = sub.add_parser('fetch')
    fetch.add_argument('--run-id', type=int, required=True)
    fetch.add_argument('--output', type=Path)
    device = sub.add_parser('device')
    device.add_argument('--folder', type=Path, required=True)
    device.add_argument('--serial', required=True)
    device.add_argument('--source-sha')
    device.add_argument('--install', action='store_true', help='Explicit guarded in-place upgrade')
    for p in (fetch, device):
        p.add_argument('--trusted-signer', help='Use exact trusted public signing cert SHA256')
    args = ap.parse_args()
    try:
        pin = pin_from_owner(args.trusted_signer)
        if args.action == 'fetch':
            demand(args.run_id > 0, 'RUN_ID_INVALID')
            folder = args.output or Path.home() / 'Downloads' / ('Skybind-Personal-APK-' + str(args.run_id))
            result = download(args.run_id, folder, pin)
        else:
            demand(SERIAL.fullmatch(args.serial) is not None, 'ADB_SERIAL_INVALID')
            demand(args.source_sha is None or SHA.fullmatch(args.source_sha) is not None,
                   'EXPECTED_SOURCE_SHA_INVALID')
            result = device_action(args.folder, args.serial, pin, do_install=args.install,
                                   sha=args.source_sha)
        result['receipt'] = save_receipt(result)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (CandidateError, ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        reason = str(exc) if isinstance(exc, CandidateError) else type(exc).__name__
        blocked = {'status': 'PERSONAL_APK_BLOCKED', 'reason': reason,
                   'installer_success_confirmed': False, 'release_qualified': False,
                   'device_qualified': False}
        try:
            blocked['receipt'] = save_receipt(blocked)
        except OSError:
            pass
        print(json.dumps(blocked, sort_keys=True))
        return 2

if __name__ == '__main__':
    sys.exit(main())
