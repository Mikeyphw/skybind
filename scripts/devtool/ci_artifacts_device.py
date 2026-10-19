#!/usr/bin/env python3
"""Skybind CI artifact -> installed pair -> selected real-device acceptance.

Adapted from Cinderbox-Companion scripts/devtool/ci_artifacts_device.py.
No implicit test selection, package removal, data clearing, reboot, forced process
termination, root-shell calls, daemon writes or release publication.

Default: download and authenticate the exact hosted debug pair and require it to
be installed byte-for-byte. --install explicitly opts into *same-signer* APK
installation/replacement only; --test m2-live explicitly opts into the app's
RootService acceptance and the root-manager consent UI.
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
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/dev/android'))
import m2_live_device as live
import apk_manifest

REPO = 'Mikeyphw/skybind'
ARTIFACT = 'skybind-android-debug-apks-unqualified'
APP = 'io.github.mikeyphw.skybind'
TEST = APP + '.test'
FILES = frozenset({'android-build-manifest.json', 'app-debug.apk', 'app-debug-androidTest.apk'})
# Only reviewed, locally registered lanes may execute. No arbitrary --command,
# arbitrary Python file, --class or user-supplied script path is accepted.
LANES = {'m2-preflight': 'preflight', 'm2-live': 'live'}
SERIAL = re.compile(r'[A-Za-z0-9_.:-]{1,128}\Z')
APK_PATH = re.compile(r'/data/app/[A-Za-z0-9_./+@=:\-~]+/base\.apk\Z')


class QualificationError(Exception):
    pass


def require(ok, code):
    if not ok:
        raise QualificationError(code)


def select_lanes(requested):
    chosen = []
    for entry in requested:
        for token in entry.split(','):
            lane = token.strip()
            require(lane in LANES, 'UNKNOWN_TEST_LANE:' + lane)
            if lane not in chosen:
                chosen.append(lane)
    return chosen


def safe_folder(folder: Path):
    require(not folder.is_symlink(), 'ARTIFACT_DIRECTORY_SYMLINK')
    if folder.exists():
        require(folder.is_dir(), 'ARTIFACT_DIRECTORY_NOT_DIRECTORY')
        for item in folder.iterdir():
            require(not item.is_symlink() and item.is_file() and item.name in FILES,
                    'UNEXPECTED_ARTIFACT_MEMBER')
    return folder


def obtain_pair(run_id: int, artifact_id: int, folder: Path):
    """GitHub-owned download. Certificate + manifest validation follows.

    GitHub exposes an artifact archive digest; gh run download extracts the archive
    without retaining ZIP bytes, so this entry point does not claim a ZIP digest
    comparison. We require authenticated run/artifact metadata and independent
    per-APK hash + cryptographic signing verification instead.
    """
    safe_folder(folder)
    if not folder.exists():
        folder.mkdir(parents=True, mode=0o700)
    files = set(p.name for p in folder.iterdir())
    if files != FILES:
        require(not files, 'PARTIAL_ARTIFACT_CACHE_REFUSED')
        live.invoke(['gh', 'run', 'download', str(run_id), '--repo', REPO,
                     '--name', ARTIFACT, '--dir', str(folder)], timeout=360)
    safe_folder(folder)
    require({p.name for p in folder.iterdir()} == FILES,
            'INCOMPLETE_HOSTED_APK_PAIR')
    for name in FILES:
        size = (folder / name).stat().st_size
        require(0 < size <= (32768 if name.endswith('.json') else 64 * 1024 * 1024),
                'HOSTED_ARTIFACT_MEMBER_SIZE_INVALID')
    return folder


def package_path(serial: str, package: str):
    proc = live.adb(serial, 'shell', 'pm', 'path', package, ok=False)
    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    if proc.returncode == 1 and not lines and not proc.stderr.strip():
        # Stock Android uses exit 1 for an absent package. Verify absence using
        # an independent PackageManager command rather than masking a PM failure.
        other = live.adb(serial, 'shell', 'pm', 'list', 'packages', '--user', '0', package)
        entries = [line.strip() for line in other.stdout.splitlines() if line.strip()]
        require(all(re.fullmatch(r'package:[A-Za-z][A-Za-z0-9_.]*', e) for e in entries),
                'PACKAGE_ENUMERATION_AMBIGUOUS')
        require(f'package:{package}' not in entries, 'PACKAGE_MANAGER_DISAGREEMENT')
        return None
    require(proc.returncode == 0 and not proc.stderr.strip(), 'PACKAGE_QUERY_FAILED')
    if not lines:
        other = live.adb(serial, 'shell', 'pm', 'list', 'packages', '--user', '0', package)
        entries = [line.strip() for line in other.stdout.splitlines() if line.strip()]
        require(f'package:{package}' not in entries, 'PACKAGE_MANAGER_DISAGREEMENT')
        return None
    require(len(lines) == 1 and lines[0].startswith('package:'),
            'SPLIT_OR_AMBIGUOUS_INSTALLED_PACKAGE')
    path = lines[0].removeprefix('package:')
    require(APK_PATH.fullmatch(path) is not None and '/../' not in path,
            'UNSAFE_INSTALLED_APK_PATH')
    return path


def installed_identity(serial: str):
    """Read-only installed package/signing inventory, never clears or mutates."""
    with tempfile.TemporaryDirectory(prefix='skybind-ci-installed-') as td:
        result = {}
        for kind, package in (('app', APP), ('test_apk', TEST)):
            path = package_path(serial, package)
            if path is None:
                result[kind] = {'present': False}
                continue
            dest = Path(td) / (kind + '.apk')
            live.adb(serial, 'pull', path, str(dest), timeout=100)
            require(dest.is_file() and not dest.is_symlink(), 'INSTALLED_APK_PULL_FAILED')
            signer = apk_manifest.apk_cert(dest)
            require(signer is not None, 'INSTALLED_SIGNING_CERTIFICATE_UNAVAILABLE')
            result[kind] = {'present': True, 'sha256': live.sha256(dest), 'signer': signer}
        return result


def installation_preflight(installed, manifest, pin: str):
    app, test = installed['app'], installed['test_apk']
    require(app['present'] == test['present'], 'PARTIAL_INSTALLED_PACKAGE_PAIR')
    if not app['present']:
        return 'ABSENT'
    require(app['signer'] == pin and test['signer'] == pin,
            'INSTALLED_SIGNER_DIFFERS_FROM_PERSISTENT_KEY')
    if (app['sha256'] == manifest['app']['sha256'] and
            test['sha256'] == manifest['test_apk']['sha256']):
        return 'MATCHED'
    return 'SAME_SIGNER_UPGRADE_NEEDED'


def install_pair(serial: str, folder: Path, state: str):
    """Explicit --install only; no uninstall, -d, -k, data clear, or shell-root."""
    require(state in ('ABSENT', 'SAME_SIGNER_UPGRADE_NEEDED'),
            'INSTALL_NOT_REQUIRED_OR_UNSAFE')
    for filename, is_test in (('app-debug.apk', False),
                              ('app-debug-androidTest.apk', True)):
        args = ['install', '-r']
        if is_test:
            args.append('-t')
        args.append(str(folder / filename))
        process = live.adb(serial, *args, timeout=180)
        require(process.stdout.strip().endswith('Success'), 'ADB_INSTALL_NOT_SUCCESSFUL')


def validated_lane_receipt(record, *, lane: str, run_id: int, sha: str, artifact_id: int):
    require(isinstance(record, dict), 'LANE_RECEIPT_INVALID')
    require(record.get('schema') == 'skybind-m2-live-v1', 'LANE_RECEIPT_SCHEMA_MISMATCH')
    require(record.get('source_sha') == sha and record.get('github_run_id') == run_id,
            'LANE_SOURCE_OR_RUN_MISMATCH')
    require(record.get('artifact_id') == artifact_id, 'LANE_ARTIFACT_MISMATCH')
    require(record.get('installed_pair_verified') is True and
            record.get('signing_verified') is True and
            record.get('release_qualified') is False and
            record.get('device_qualified') is False,
            'LANE_PROVENANCE_OR_SCOPE_MISMATCH')
    expected = ('PASS_M2_L1_PAIR_PREFLIGHT_ONLY' if lane == 'm2-preflight'
                else 'PASS_M2_L1_LIVE_READ_BROWSE_REBIND')
    require(record.get('state') == expected, 'TEST_LANE_NOT_PASS:' + lane)
    require(bool(record.get('m2_l1_device_qualified')) == (lane == 'm2-live'),
            'LANE_QUALIFICATION_OVERCLAIM')
    return {'state': expected, 'receipt': record.get('receipt'),
            'qualified_scope': record.get('qualified_scope') if lane == 'm2-live' else None}


def execute_lane(lane: str, run_id: int, serial: str, folder: Path, remote: str | None,
                 sha: str, artifact_id: int):
    # m2_live_device is the canonical isolated test implementation. Never
    # duplicate its instrumentation parser or change its root approval policy.
    import contextlib
    import io
    opts = argparse.Namespace(run_id=run_id, mode=LANES[lane], serial=serial,
                              artifact_dir=folder, remote=remote)
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = live.run(opts)
    lines = [l for l in output.getvalue().splitlines() if l.strip()]
    require(lines, 'LANE_RECEIPT_NOT_REPORTED')
    summary = json.loads(lines[-1])
    receipt = summary.get('receipt')
    require(isinstance(receipt, str) and receipt, 'LANE_RECEIPT_NOT_REPORTED')
    path = Path(receipt)
    require(path.is_file() and not path.is_symlink() and
            path.stat().st_size <= 16384, 'LANE_RECEIPT_UNAVAILABLE')
    doc = json.loads(path.read_text())
    require(doc.get('receipt') == receipt and summary.get('state') == doc.get('state'),
            'LANE_RECEIPT_SUMMARY_MISMATCH')
    if code != 0:
        classification = ('FAILED' if doc.get('state') == 'FAILED' else 'BLOCKED')
        raise QualificationError('TEST_LANE_' + classification + ':' + lane + ':' +
                                 str(doc.get('reason'))[:64])
    return validated_lane_receipt(doc, lane=lane, run_id=run_id, sha=sha,
                                  artifact_id=artifact_id)


def store_report(root: Path, obj: dict):
    require(not root.is_symlink(), 'OUTPUT_ROOT_SYMLINK')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    dest = root / ('ci-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
                   + '-' + uuid.uuid4().hex[:8])
    dest.mkdir(mode=0o700)
    path = dest / 'summary.json'
    with path.open('x', encoding='utf-8') as f:
        json.dump(obj, f, sort_keys=True, indent=2)
        f.write('\n')
    path.chmod(0o600)
    return str(path)


def run(args):
    selected = select_lanes(args.test)
    require(args.run_id > 0, 'RUN_ID_INVALID')
    require(args.expected_sha is None or live.SHA.fullmatch(args.expected_sha),
            'EXPECTED_SOURCE_SHA_INVALID')
    require(args.serial is None or SERIAL.fullmatch(args.serial), 'ADB_SERIAL_INVALID')
    require(args.remote is None or live.PATTERN.fullmatch(args.remote), 'REMOTE_NAME_INVALID')
    doc = dict(schema='skybind-ci-artifacts-device-v1', status='BLOCKED', reason=None,
               github_run_id=args.run_id, source_sha=None, github_run_authenticated=False,
               artifact_metadata_verified=False, signing_verified=False,
               installed_pair_verified=False, installation_performed=False,
               automatic_uninstall=False, automatic_data_clear=False,
               root_grant_changed_by_runner=False, daemon_mutated=False,
               selected_lanes=selected, tests={}, device_qualified=False,
               release_qualified=False,
               recorded_at_utc=datetime.now(timezone.utc).isoformat())
    try:
        sha = live.current_source()
        doc['source_sha'] = sha
        require(args.expected_sha is None or args.expected_sha == sha,
                'LOCAL_SOURCE_SHA_MISMATCH')
        artifact = live.github(args.run_id, sha)
        doc['github_run_authenticated'] = True
        doc['artifact_metadata_verified'] = True
        doc['artifact_id'] = artifact['id']
        doc['artifact_digest'] = artifact['digest']
        folder = args.artifact_dir or (Path.home()/'.cache/skybind'/f'hosted-{args.run_id}')
        obtain_pair(args.run_id, artifact['id'], folder)
        pin = live.read_pin()
        manifest = live.verify_candidate(folder, args.run_id, sha, pin)
        doc.update(signing_verified=True, app_sha256=manifest['app']['sha256'],
                   test_sha256=manifest['test_apk']['sha256'])
        serial = live.choose_device(args.serial)
        doc['device_serial_sha256'] = hashlib.sha256(serial.encode()).hexdigest()
        device_api = live.adb(serial, 'shell', 'getprop', 'ro.build.version.sdk').stdout.strip()
        require(device_api.isdecimal() and int(device_api) >= 28, 'DEVICE_API_UNSUPPORTED')
        doc['device_api'] = int(device_api)
        require(live.adb(serial, 'shell', 'getenforce').stdout.strip() == 'Enforcing',
                'DEVICE_SELINUX_NOT_ENFORCING')
        state = installation_preflight(installed_identity(serial), manifest, pin)
        doc['installed_before'] = state
        if state != 'MATCHED':
            require(args.install, 'EXPLICIT_INSTALL_REQUIRED')
            install_pair(serial, folder, state)
            doc['installation_performed'] = True
        live.installed_pair(serial, manifest, pin)
        doc['installed_pair_verified'] = True
        for lane in selected:
            try:
                doc['tests'][lane] = execute_lane(lane, args.run_id, serial, folder, args.remote,
                                                  sha, artifact['id'])
            except (QualificationError, live.Blocked) as exc:
                reason = str(exc) if isinstance(exc, QualificationError) else exc.reason
                doc['tests'][lane] = {'state': ('FAILED' if reason.startswith('TEST_LANE_FAILED:')
                                              else 'BLOCKED'), 'reason': reason[:128]}
                raise
        doc['status'] = ('PASS_CI_PAIR_AND_SELECTED_LANES' if selected
                         else 'PASS_CI_PAIR_VERIFIED_NO_TESTS_SELECTED')
        doc['m2_l1_device_qualified'] = (doc['tests'].get('m2-live', {}).get('state') ==
                                         'PASS_M2_L1_LIVE_READ_BROWSE_REBIND')
    except (QualificationError, live.Blocked, OSError, ValueError, KeyError, TypeError,
            json.JSONDecodeError) as exc:
        doc['reason'] = (str(exc) if isinstance(exc, QualificationError) else
                         exc.reason if isinstance(exc, live.Blocked) else
                         type(exc).__name__.upper())[:160]
        if doc['reason'].startswith('TEST_LANE_FAILED:'):
            doc['status'] = 'FAILED'
    doc['receipt'] = store_report(args.output_root, doc)
    print(json.dumps({key: doc.get(key) for key in
                     ('status','reason','receipt','github_run_id','artifact_id','source_sha',
                      'installed_before','installed_pair_verified','installation_performed',
                      'selected_lanes','tests','m2_l1_device_qualified')}, sort_keys=True))
    return 0 if doc['status'].startswith('PASS_') else 2


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-id', type=int, help='Exact successful hosted GitHub run ID')
    p.add_argument('--expected-sha', help='Optional exact SHA pin in addition to local HEAD')
    p.add_argument('--serial', default=os.environ.get('ADB_SERIAL'),
                   help='ADB serial (or ADB_SERIAL); omit only with one connected device')
    p.add_argument('--remote', help='Explicit configured remote for --test m2-live')
    p.add_argument('--artifact-dir', type=Path, help='Authenticated artifact cache path')
    p.add_argument('--output-root', type=Path,
                   default=Path.home()/'.local/state/skybind/ci-artifacts-device')
    p.add_argument('--test', action='append', default=[],
                   help='Only selected reviewed lanes; repeat or comma-separate')
    p.add_argument('--list-tests', action='store_true', help='List supported device lanes')
    install = p.add_mutually_exclusive_group()
    install.add_argument('--install', action='store_true',
                         help='Explicitly allow same-signer APK install/update, no uninstall')
    install.add_argument('--skip-install', action='store_true',
                         help='Verify installed APKs only (default behavior)')
    args = p.parse_args(argv)
    if args.list_tests:
        for name in sorted(LANES):
            print(name)
        return 0
    if not args.run_id:
        p.error('--run-id required unless --list-tests')
    return run(args)


if __name__ == '__main__':
    raise SystemExit(main())
