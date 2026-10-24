#!/usr/bin/env python3
"""NATIVE-06 personal APK acceptance and owner approval (no APK installation).

An owner-scoped, fail-closed evidence recorder. It cannot create GitHub builds,
authorize root, install packages, prepare fixtures, or certify untested devices.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid
import zipfile
import m3_adb_fixture

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
from personal_apk import (APP, TEST, MANIFEST_FILE, SHA, CandidateError, demand)
from personal_apk_device import (verify_folder, inspect_installed, pin_from_owner, gh_info,
                                 adb, SERIAL)

SCHEMA = 'skybind-native-personal-device-acceptance-v1'
RUNNER = TEST + '/androidx.test.runner.AndroidJUnitRunner'
MANAGERS = ('kernelsu', 'kernelsu-next', 'magisk', 'apatch', 'other')
CASE = APP + '.'
# No generic test-package scan: an exact invocation and an exact passing method
# is required. A skipped/assumed test is NEVER an acceptance PASS.
BASE_LANES = (
    ('navigation', 'NativeUiTest#realNavigationHasFiveDistinctPages', None),
    ('mount-ui', 'NativeUiTest#mountActionsRequireUserGestureAndExplicitConsent', None),
    ('mount-consent', 'NativeUiTest#mountConfirmationNeverRunsWithoutCheckboxConsent', None),
    ('config-consent', 'NativeUiTest#configApplyRequiresReviewConsent', None),
    ('polish', 'NativePolishUiTest#diagnosticsAndBkxStatesAreVisibleWithoutBackgroundActivation', None),
    ('auto-root', 'NativePersonalLiveTest#automaticForegroundRootNoManualConnect', 'skybind.native.personal.live'),
    ('mount-live', 'NativePersonalLiveTest#mountsMatchAuthoritativeDaemon', 'skybind.native.personal.live'),
    ('browser-live', 'LiveRootBrowserAcceptanceTest#liveReadBrowseAndReconnect', 'skybind.live'),
    ('ui-live', 'LiveUiAcceptanceTest#liveUiReadOnlyNavigationRecovery', 'skybind.ui.live'),
    ('negative-live', 'LiveNegativeAcceptanceTest#liveReadOnlyNegativeBoundaries', 'skybind.negative.live'),
    ('transport-live', 'LiveTransportAcceptanceTest#liveTransportLossAndFreshReconnect', 'skybind.transport.live'),
    ('m3-preview', 'LiveM3PreviewAcceptanceTest#liveM3ReadOnlyJobPreview', 'skybind.m3.preview.live'),
)
WRITE_LANES = (
    ('config-disposable', 'NativeMountConfigLiveTest#guardedDisposableCreateEditRollbackDelete', 'skybind.native.config.allow_disposable'),
    ('mount-lifecycle', 'NativePersonalLiveTest#disposableMountStartRestartStopReconcile', 'skybind.native.personal.lifecycle'),
    ('m3-check', 'LiveM3DisposableAcceptanceTest#liveDisposableCheckCompletes', 'skybind.m3.execute.live'),
    ('m3-cancel', 'LiveM3DisposableAcceptanceTest#liveDisposableOwnedCancellation', 'skybind.m3.cancel.live'),
    ('m3-copy', 'LiveM3CopyAcceptanceTest#liveDisposableCopyReconnectReconcile', 'skybind.m3.copy.live'),
)
REQUIRED_FULL = tuple(x[0] for x in BASE_LANES + WRITE_LANES) + ('cold-relaunch',)
STATUS = re.compile(r'^INSTRUMENTATION_STATUS_CODE:\s*(-?\d+)\s*$', re.M)
FINAL = re.compile(r'^INSTRUMENTATION_CODE:\s*(-?\d+)\s*$', re.M)


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda: stream.read(1024*1024), b''):
            digest.update(part)
    return digest.hexdigest()


def source_sha() -> str:
    result = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'],
                            capture_output=True, text=True, timeout=20)
    demand(result.returncode == 0 and SHA.fullmatch(result.stdout.strip()) is not None,
           'LOCAL_SOURCE_COMMIT_UNAVAILABLE')
    clean = subprocess.run(['git', '-C', str(ROOT), 'status', '--porcelain', '--untracked-files=normal'],
                           capture_output=True, text=True, timeout=20)
    demand(clean.returncode == 0 and not clean.stdout.strip(), 'RUNNER_SOURCE_DIRTY')
    return result.stdout.strip()


def parse_instrumentation(case: str, output: str, rc: int) -> str:
    method = case.rsplit('#', 1)[1]
    codes = STATUS.findall(output)
    done = FINAL.findall(output)
    demand(rc == 0 and done == ['-1'] and codes == ['1', '0'] and
           'INSTRUMENTATION_STATUS: test=' + method in output and
           'INSTRUMENTATION_STATUS: numtests=1' in output and
           'OK (1 test)' in output and 'FAILURES!!!' not in output and
           'SKYBIND_' not in '\n'.join(line for line in output.splitlines()
                                            if 'BLOCKED_' in line or 'FAILED_' in line),
           'INSTRUMENTATION_FAILED_OR_SKIPPED:' + method)
    return sha256_bytes(output.encode('utf-8'))


def instrument(serial: str, case: str, extra: dict[str, str], timeout=180) -> dict:
    name = CASE + case
    demand(re.fullmatch(r'[A-Za-z][A-Za-z0-9]+Test#[A-Za-z][A-Za-z0-9]+', case) is not None,
           'TEST_CASE_UNEXPECTED')
    args = ['adb', '-s', serial, 'shell', 'am', 'instrument', '-w', '-r', '-e', 'class', name]
    for k, v in sorted(extra.items()):
        demand(re.fullmatch(r'skybind\.[a-z0-9._]+', k) is not None and
               re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', v) is not None,
               'INSTRUMENT_ARGUMENT_UNSAFE')
        args += ['-e', k, v]
    args.append(RUNNER)
    try:
        proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CandidateError('INSTRUMENTATION_EXECUTION_FAILED:' + case) from exc
    output = proc.stdout + '\n' + proc.stderr
    digest = parse_instrumentation(case, output, proc.returncode)
    return {'status': 'PASS', 'case': name, 'instrumentation_sha256': digest}


def plan(profile: str, *, remote: str | None, consent_config: bool,
         consent_jobs: bool, consent_stop: bool, consent_reconcile: bool):
    if profile == 'readonly':
        demand(not (consent_config or consent_jobs or consent_stop or consent_reconcile),
               'READONLY_MUST_NOT_HAVE_MUTATION_CONSENT')
        return BASE_LANES
    demand(profile == 'full' and bool(remote) and
           all((consent_config, consent_jobs, consent_stop, consent_reconcile)),
           'FULL_REQUIRES_FOUR_SEPARATE_CONSENTS_AND_REMOTE')
    demand(re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', remote or '') is not None,
           'TEST_REMOTE_INVALID')
    return BASE_LANES + WRITE_LANES


def preflight(folder: Path, serial: str, signer: str):
    manifest, verified = verify_folder(folder, sha=None, run_id=None, pin=signer)
    current = source_sha()
    demand(current == manifest['source_sha'], 'EXACT_COMMITTED_APK_SOURCE_REQUIRED')
    demand(gh_info(manifest['run_id']) == current, 'HOSTED_WORKFLOW_SOURCE_MISMATCH')
    installed = inspect_installed(serial, manifest, signer)
    demand(installed['state'] == 'ALREADY_INSTALLED_IDENTICAL_PAIR',
           'EXACT_SIGNED_PERSONAL_APP_AND_TEST_NOT_INSTALLED')
    demand(adb(serial, 'get-state').strip() == 'device', 'ADB_DEVICE_NOT_ONLINE')
    api = adb(serial, 'shell', 'getprop', 'ro.build.version.sdk').strip()
    demand(api.isdecimal() and int(api) >= 35, 'ANDROID_35_PLUS_REQUIRED')
    demand(adb(serial, 'shell', 'getenforce').strip() == 'Enforcing',
           'SELINUX_ENFORCING_REQUIRED')
    return manifest, int(api)


def run_cold_relaunch(serial: str) -> dict:
    # Explicit app-only process disruption; no daemon kill or root revocation.
    p = adb(serial, 'shell', 'am', 'start', '-W', '-n', APP + '/.MainActivity')
    demand('Error:' not in p, 'APP_LAUNCH_FAILED')
    old = adb(serial, 'shell', 'pidof', APP).strip()
    demand(re.fullmatch(r'[0-9\s]+', old) is not None, 'APP_PID_NOT_OBSERVED')
    adb(serial, 'shell', 'am', 'force-stop', APP)
    stopped = subprocess.run(['adb', '-s', serial, 'shell', 'pidof', APP],
                             capture_output=True, text=True, timeout=15)
    demand(stopped.returncode != 0 and not stopped.stdout.strip(), 'APP_NOT_STOPPED')
    adb(serial, 'shell', 'am', 'start', '-W', '-n', APP + '/.MainActivity')
    fresh = adb(serial, 'shell', 'pidof', APP).strip()
    demand(bool(fresh) and not set(old.split()) & set(fresh.split()), 'APP_COLD_PID_NOT_NEW')
    return {'status': 'PASS', 'old_pid_sha256': sha256_bytes(old.encode()),
            'new_pid_sha256': sha256_bytes(fresh.encode())}


def safe_store(payload: dict, directory: Path, prefix: str) -> Path:
    demand(not directory.is_symlink(), 'RECEIPT_DIRECTORY_SYMLINK')
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    demand(not directory.is_symlink() and directory.stat().st_mode & 0o077 == 0,
           'RECEIPT_DIRECTORY_PERMISSIONS_UNSAFE')
    path = directory / (prefix + uuid.uuid4().hex + '.json')
    with path.open('x') as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write('\n')
    path.chmod(0o600)
    return path


def verify_matching_module(serial: str, json_path: Path, zip_path: Path, source: str) -> dict:
    """Same-source native module must be installed, not merely built or approved before."""
    demand(json_path.is_file() and not json_path.is_symlink() and
           json_path.stat().st_size < 20000 and zip_path.is_file() and
           not zip_path.is_symlink() and 100 < zip_path.stat().st_size < 512*1024*1024,
           'MATCHING_MODULE_BUILD_EVIDENCE_REQUIRED')
    meta = json.loads(json_path.read_text())
    demand(meta.get('status') == 'VERIFIED_LOCAL_BUILD_FOR_PERSONAL_USE' and
           meta.get('personal_release_policy') == 'SKYBIND_PERSONAL_V1' and
           meta.get('source', {}).get('commit') == source and
           meta.get('provider') in ('bclone', 'newfuture') and
           meta.get('archive') == zip_path.name,
           'MODULE_SOURCE_OR_PROVENANCE_MISMATCH')
    archive_hash = sha256_file(zip_path)
    demand(archive_hash == meta.get('archive_sha256'), 'MODULE_ARCHIVE_DIGEST_MISMATCH')
    with zipfile.ZipFile(zip_path) as archive:
        demand(archive.testzip() is None, 'MODULE_ZIP_CORRUPTED')
        info = archive.getinfo('system/bin/skybind')
        demand(0 < info.file_size < 80_000_000, 'MODULE_BINARY_SIZE_INVALID')
        binary_sha = sha256_bytes(archive.read(info))
    # ADB transport does not infer root authority. Try already-rooted shell first,
    # then the actual device root manager's su. Both are read-only and fixed-path.
    target = '/data/adb/modules/skybind/system/bin/skybind'
    commands = ([ 'adb', '-s', serial, 'shell', '/system/bin/sha256sum', target ],
                [ 'adb', '-s', serial, 'shell', 'su', '-c',
                 '/system/bin/sha256sum /data/adb/modules/skybind/system/bin/skybind' ])
    observed = None
    for cmd in commands:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if proc.returncode == 0:
            match = re.fullmatch(r'([0-9a-f]{64})\s+'+re.escape(target)+r'\s*', proc.stdout)
            if match:
                observed = match.group(1)
                break
    demand(observed == binary_sha, 'INSTALLED_NATIVE_DAEMON_BINARY_MISMATCH_OR_UNREADABLE')
    return {'module_archive_sha256': archive_hash, 'module_binary_sha256': binary_sha,
            'installed_module_verified': True, 'module_provider': meta['provider']}


def acceptance(args):
    lanes = plan(args.profile, remote=args.remote,
                 consent_config=args.allow_disposable_config,
                 consent_jobs=args.allow_disposable_jobs,
                 consent_stop=args.allow_app_force_stop,
                 consent_reconcile=args.allow_global_reconcile)
    pin = pin_from_owner(args.trusted_signer)
    manifest, api = preflight(args.folder, args.serial, pin)
    demand(args.profile != 'full' or (args.module_manifest is not None and
           args.module_zip is not None), 'FULL_REQUIRES_MATCHING_MODULE_ARTIFACT')
    module = (verify_matching_module(args.serial, args.module_manifest, args.module_zip,
                                     manifest['source_sha']) if args.profile == 'full' else None)
    doc = {'schema': SCHEMA, 'status': 'NATIVE_APK_DEVICE_ACCEPTANCE_INCOMPLETE',
           'profile': args.profile, 'source_sha': manifest['source_sha'],
           'github_run_id': manifest['run_id'], 'app_sha256': manifest['app']['sha256'],
           'test_sha256': manifest['test_apk']['sha256'], 'signer_sha256': pin,
           'device_serial_sha256': sha256_bytes(args.serial.encode()),
           'device_api': api, 'root_manager': args.manager,
           'candidate_version_code': manifest['requested_version_code'],
           'module': module, 'lanes': {}, 'device_qualified': False, 'release_qualified': False,
           'owner_approval': False, 'independent_attestation': False,
           'observed_at_utc': datetime.now(timezone.utc).isoformat()}
    base = {'skybind.remote': args.remote} if args.remote else {}
    try:
        if args.profile == 'full':
            # Reuse target-side independently hashed fixtures. Never prepare them here.
            m3_adb_fixture.verify(args.serial, 'check', 'prepared')
            m3_adb_fixture.verify(args.serial, 'copy', 'prepared')
        for key, method, opt_in in lanes:
            options = dict(base)
            if opt_in:
                options[opt_in] = 'true'
            if key == 'mount-lifecycle':
                options['skybind.native.personal.reconcile'] = 'true'
                options['skybind.native.personal.remote'] = args.remote
            if key == 'config-disposable':
                options['skybind.native.config.remote'] = args.remote
            doc['lanes'][key] = instrument(args.serial, method, options, timeout=360)
        if args.profile == 'full':
            doc['lanes']['cold-relaunch'] = run_cold_relaunch(args.serial)
            # Requalify real automatic root binding after deliberate cold launch.
            doc['lanes']['auto-root-after-cold'] = instrument(args.serial,
                'NativePersonalLiveTest#automaticForegroundRootNoManualConnect',
                {'skybind.native.personal.live': 'true'}, timeout=180)
            demand(set(REQUIRED_FULL).issubset(doc['lanes']) and
                   all(x['status'] == 'PASS' for x in doc['lanes'].values()),
                   'REQUIRED_DEVICE_LANE_MISSING')
            doc['status'] = 'PASS_NATIVE_PERSONAL_DEVICE_FULL'
            doc['device_qualified'] = True
        else:
            doc['status'] = 'PASS_NATIVE_PERSONAL_READONLY_ONLY_NOT_QUALIFIED'
    except (CandidateError, m3_adb_fixture.Blocked, OSError, ValueError, KeyError, AssertionError) as exc:
        doc['status'] = 'NATIVE_APK_DEVICE_ACCEPTANCE_BLOCKED'
        doc['reason'] = str(exc) if isinstance(exc, (CandidateError, m3_adb_fixture.Blocked)) else type(exc).__name__
    path = safe_store(doc, args.receipt_dir, 'native06-')
    return doc, path


def checked_full_receipt(receipt: dict, manifest: dict, trusted: str) -> None:
    demand(receipt.get('schema') == SCHEMA and
           receipt.get('profile') == 'full' and
           receipt.get('status') == 'PASS_NATIVE_PERSONAL_DEVICE_FULL' and
           receipt.get('device_qualified') is True and
           receipt.get('release_qualified') is False and
           receipt.get('owner_approval') is False and
           receipt.get('independent_attestation') is False,
           'FULL_DEVICE_RECEIPT_NOT_ACCEPTED')
    demand(receipt.get('source_sha') == manifest['source_sha'] and
           receipt.get('github_run_id') == manifest['run_id'] and
           receipt.get('app_sha256') == manifest['app']['sha256'] and
           receipt.get('test_sha256') == manifest['test_apk']['sha256'] and
           receipt.get('signer_sha256') == trusted and
           receipt.get('candidate_version_code') == manifest['requested_version_code'] and
           receipt.get('root_manager') in MANAGERS and
           type(receipt.get('device_api')) is int and receipt['device_api'] >= 35 and
           re.fullmatch('[0-9a-f]{64}', str(receipt.get('device_serial_sha256',''))) is not None,
           'DEVICE_RECEIPT_APK_IDENTITY_MISMATCH')
    mod = receipt.get('module')
    demand(isinstance(mod, dict) and mod.get('installed_module_verified') is True and
           re.fullmatch('[0-9a-f]{64}', str(mod.get('module_archive_sha256',''))) is not None and
           re.fullmatch('[0-9a-f]{64}', str(mod.get('module_binary_sha256',''))) is not None and
           mod.get('module_provider') in ('bclone', 'newfuture'),
           'SAME_SOURCE_INSTALLED_MODULE_EVIDENCE_MISSING')
    entries = receipt.get('lanes')
    demand(isinstance(entries, dict) and set(REQUIRED_FULL).issubset(entries) and
           'auto-root-after-cold' in entries and all(isinstance(v, dict) and
           v.get('status') == 'PASS' for v in entries.values()),
           'DEVICE_ACCEPTANCE_LANES_INCOMPLETE')
    cases = {key: CASE + method for key, method, _ in BASE_LANES + WRITE_LANES}
    cases['auto-root-after-cold'] = CASE + 'NativePersonalLiveTest#automaticForegroundRootNoManualConnect'
    demand(set(entries) == set(cases) | {'cold-relaunch'},
           'UNEXPECTED_OR_MISSING_ACCEPTANCE_LANE')
    for key, case in cases.items():
        observation = entries[key]
        demand(observation.get('case') == case and
               re.fullmatch('[0-9a-f]{64}', str(observation.get('instrumentation_sha256',''))) is not None,
               'RECEIPT_TEST_CASE_OR_LOG_DIGEST_MISMATCH:' + key)
    cold = entries['cold-relaunch']
    demand(all(re.fullmatch('[0-9a-f]{64}', str(cold.get(name, ''))) is not None
               for name in ('old_pid_sha256', 'new_pid_sha256')) and
           cold['old_pid_sha256'] != cold['new_pid_sha256'],
           'COLD_RELAUNCH_PROCESS_EVIDENCE_MISSING')


def owner_approve(args):
    demand(args.ui_reviewed and args.root_approved and args.mount_reviewed and
           args.accept_personal_scope and args.accept_untested_managers,
           'EXPLICIT_ALL_OWNER_APPROVAL_FLAGS_REQUIRED')
    pin = pin_from_owner(args.trusted_signer)
    manifest, _ = verify_folder(args.folder, sha=source_sha(), run_id=None, pin=pin)
    demand(args.device_receipt.is_file() and not args.device_receipt.is_symlink() and
           args.device_receipt.stat().st_size <= 50000, 'DEVICE_RECEIPT_FILE_INVALID')
    raw = args.device_receipt.read_bytes()
    receipt = json.loads(raw)
    checked_full_receipt(receipt, manifest, pin)
    # Verify immutable receipt is an actual operator-run file in controlled state directory.
    accepted_dir = (Path.home() / '.local/state/skybind/native-personal').resolve()
    demand(args.device_receipt.resolve().parent == accepted_dir,
           'RECEIPT_NOT_FROM_OPERATOR_STATE_DIRECTORY')
    demand(gh_info(manifest['run_id']) == manifest['source_sha'], 'HOSTED_RUN_DRIFT')
    approval = {'schema': 'skybind-native-personal-approval-v1',
                'status': 'PERSONAL_NATIVE_APK_APPROVED',
                'device_receipt_sha256': sha256_bytes(raw),
                'source_sha': manifest['source_sha'], 'run_id': manifest['run_id'],
                'app_sha256': manifest['app']['sha256'],
                'test_sha256': manifest['test_apk']['sha256'],
                'signer_sha256': pin, 'module': receipt['module'],
                'root_manager': receipt['root_manager'],
                'device_serial_sha256': receipt['device_serial_sha256'],
                'personal_scope_only': True, 'independent_certification_claimed': False,
                'untested_managers_not_qualified': True, 'owner_approval': True,
                'approved_at_utc': datetime.now(timezone.utc).isoformat()}
    return approval, safe_store(approval, args.receipt_dir, 'approval-')


def approval_check(args):
    pin = pin_from_owner(args.trusted_signer)
    manifest, _ = verify_folder(args.folder, sha=source_sha(), run_id=None, pin=pin)
    demand(args.approval.is_file() and not args.approval.is_symlink() and
           args.approval.stat().st_size < 10000, 'APPROVAL_FILE_INVALID')
    demand(args.approval.resolve().parent ==
           (Path.home() / '.local/state/skybind/native-personal').resolve(),
           'APPROVAL_NOT_IN_OPERATOR_STATE_DIRECTORY')
    approval = json.loads(args.approval.read_text())
    demand(approval.get('schema') == 'skybind-native-personal-approval-v1' and
           approval.get('status') == 'PERSONAL_NATIVE_APK_APPROVED' and
           approval.get('owner_approval') is True and
           approval.get('independent_certification_claimed') is False and
           approval.get('personal_scope_only') is True and
           approval.get('app_sha256') == manifest['app']['sha256'] and
           approval.get('test_sha256') == manifest['test_apk']['sha256'] and
           approval.get('signer_sha256') == pin and
           approval.get('source_sha') == manifest['source_sha'] and
           approval.get('run_id') == manifest['run_id'], 'APPROVAL_ARTIFACT_DRIFT')
    evidence_dir = Path.home() / '.local/state/skybind/native-personal'
    digest = approval.get('device_receipt_sha256')
    found = False
    if isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest):
        for candidate in evidence_dir.glob('native06-*.json'):
            if candidate.is_symlink() or candidate.stat().st_size > 50000:
                continue
            raw = candidate.read_bytes()
            if sha256_bytes(raw) == digest:
                checked_full_receipt(json.loads(raw), manifest, pin)
                demand(approval.get('module') == json.loads(raw)['module'],
                       'APPROVED_MODULE_IDENTITY_DRIFT')
                found = True
                break
    demand(found, 'BOUND_FULL_DEVICE_EVIDENCE_MISSING')
    demand(gh_info(manifest['run_id']) == manifest['source_sha'], 'HOSTED_RUN_DRIFT')
    return {'status': 'PERSONAL_NATIVE_APK_APPROVED', 'source_sha': manifest['source_sha'],
            'app_sha256': manifest['app']['sha256'], 'run_id': manifest['run_id'],
            'independent_certification_claimed': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    for name in ('run', 'approve', 'check'):
        p = sub.add_parser(name)
        p.add_argument('--folder', type=Path, required=True)
        p.add_argument('--trusted-signer')
        p.add_argument('--receipt-dir', type=Path, default=Path.home()/'.local/state/skybind/native-personal')
        if name == 'run':
            p.add_argument('--serial', required=True)
            p.add_argument('--manager', required=True, choices=MANAGERS)
            p.add_argument('--profile', choices=('readonly', 'full'), default='readonly')
            p.add_argument('--remote')
            p.add_argument('--module-manifest', type=Path)
            p.add_argument('--module-zip', type=Path)
            p.add_argument('--allow-disposable-config', action='store_true')
            p.add_argument('--allow-disposable-jobs', action='store_true')
            p.add_argument('--allow-app-force-stop', action='store_true')
            p.add_argument('--allow-global-reconcile', action='store_true')
        if name == 'approve':
            p.add_argument('--device-receipt', required=True, type=Path)
            for option in ('ui-reviewed', 'root-approved', 'mount-reviewed',
                           'accept-personal-scope', 'accept-untested-managers'):
                p.add_argument('--'+option, action='store_true')
        if name == 'check':
            p.add_argument('--approval', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.action == 'run':
            demand(SERIAL.fullmatch(args.serial) is not None, 'ADB_SERIAL_INVALID')
            result, path = acceptance(args)
            response = {'status': result['status'], 'receipt': str(path),
                        'device_qualified': result['device_qualified'],
                        'completed_lanes': list(result['lanes'])}
            if 'reason' in result:
                response['reason'] = result['reason']
        elif args.action == 'approve':
            result, path = owner_approve(args)
            response = {'status': result['status'], 'approval': str(path),
                        'app_sha256': result['app_sha256']}
        else:
            response = approval_check(args)
        print(json.dumps(response, sort_keys=True))
        return 0 if response['status'] not in ('NATIVE_APK_DEVICE_ACCEPTANCE_BLOCKED',) else 2
    except (CandidateError, OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        reason = str(exc) if isinstance(exc, CandidateError) else type(exc).__name__
        print(json.dumps({'status': 'NATIVE_PERSONAL_BLOCKED', 'reason': reason,
                          'device_qualified': False, 'release_qualified': False}, sort_keys=True))
        return 2

if __name__ == '__main__':
    sys.exit(main())
