#!/usr/bin/env python3
"""Exact hosted-pair device acceptance: M2 read paths and opt-in M3.

No local APK build, install, uninstall, data clear, force-stop, or shell-root
invocation here. Read-only lanes never mutate the daemon. M3 disposable CHECK
execution/cancellation changes test-owned job state ONLY after explicit lane
selection and authorization; neither is a default. Historical M2 passes remain.
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
import uuid

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

REPOSITORY = 'Mikeyphw/skybind'
ARTIFACT = 'skybind-android-debug-apks-unqualified'
APP = 'io.github.mikeyphw.skybind'
TEST_APP = APP + '.test'
CASE = APP + '.LiveRootBrowserAcceptanceTest#liveReadBrowseAndReconnect'
UI_CASE = APP + '.LiveUiAcceptanceTest#liveUiReadOnlyNavigationRecovery'
NEGATIVE_CASE = APP + '.LiveNegativeAcceptanceTest#liveReadOnlyNegativeBoundaries'
TRANSPORT_CASE = APP + '.LiveTransportAcceptanceTest#liveTransportLossAndFreshReconnect'
M3_CASE = APP + '.LiveM3PreviewAcceptanceTest#liveM3ReadOnlyJobPreview'
M3_EXECUTE_CASE = APP + '.LiveM3DisposableAcceptanceTest#liveDisposableCheckCompletes'
M3_CANCEL_CASE = APP + '.LiveM3DisposableAcceptanceTest#liveDisposableOwnedCancellation'
M3_COPY_CASE = APP + '.LiveM3CopyAcceptanceTest#liveDisposableCopyReconnectReconcile'
M3_COPY_BLOCKED = ('SKYBIND_M3_COPY_NOT_REQUESTED','SKYBIND_M3_COPY_BLOCKED_BIND','SKYBIND_M3_COPY_BLOCKED_FIXTURE')
M3_COPY_FAILED = ('SKYBIND_M3_COPY_FAILED_PREVIEW_IDENTITY','SKYBIND_M3_COPY_FAILED_START',
    'SKYBIND_M3_COPY_FAILED_DUPLICATE_ACCEPTED','SKYBIND_M3_COPY_FAILED_STALE_SNAPSHOT',
    'SKYBIND_M3_COPY_FAILED_CROSS_SESSION_CANCEL_ACCEPTED','SKYBIND_M3_COPY_FAILED_STALE_PROOF_ACCEPTED',
    'SKYBIND_M3_COPY_FAILED_RECONNECT_SNAPSHOT','SKYBIND_M3_COPY_FAILED_TERMINAL_TIMEOUT',
    'SKYBIND_M3_COPY_FAILED_TERMINAL','SKYBIND_M3_COPY_FAILED_EVENT_REPLAY')

def parse_m3_copy(stdout):
    for marker in M3_COPY_FAILED:
        if marker in stdout: return 'FAILED',marker
    for marker in M3_COPY_BLOCKED:
        if marker in stdout: return 'BLOCKED',marker
    final,codes=FINAL.findall(stdout),CODES.findall(stdout)
    if '-3' in codes: return 'BLOCKED','COPY_TEST_SKIPPED'
    if (final==['-1'] and codes==['1','0'] and
            'INSTRUMENTATION_STATUS: test=liveDisposableCopyReconnectReconcile' in stdout and
            'INSTRUMENTATION_STATUS: numtests=1' in stdout and 'FAILURES!!!' not in stdout):
        return 'PASS_M3_DISPOSABLE_COPY_RECONCILED',None
    return 'FAILED','COPY_INSTRUMENTATION_INCOMPLETE'

M3_DISPOSABLE_BLOCKED = ('SKYBIND_M3_DISPOSABLE_NOT_REQUESTED',
    'SKYBIND_M3_DISPOSABLE_BLOCKED_BIND', 'SKYBIND_M3_DISPOSABLE_BLOCKED_SNAPSHOT',
    'SKYBIND_M3_DISPOSABLE_BLOCKED_FIXTURE', 'SKYBIND_M3_DISPOSABLE_BLOCKED_CANCEL_RACE')
M3_DISPOSABLE_FAILED = ('SKYBIND_M3_DISPOSABLE_FAILED_PREVIEW',
    'SKYBIND_M3_DISPOSABLE_FAILED_FIXTURE_IDENTITY', 'SKYBIND_M3_DISPOSABLE_FAILED_START',
    'SKYBIND_M3_DISPOSABLE_FAILED_REPLAY_ACCEPTED',
    'SKYBIND_M3_DISPOSABLE_FAILED_LOST_SNAPSHOT',
    'SKYBIND_M3_DISPOSABLE_FAILED_TERMINAL_TIMEOUT',
    'SKYBIND_M3_DISPOSABLE_FAILED_TERMINAL',
    'SKYBIND_M3_DISPOSABLE_FAILED_AUTHORITATIVE_JOB',
    'SKYBIND_M3_DISPOSABLE_FAILED_EVENT_REPLAY',
    'SKYBIND_M3_DISPOSABLE_FAILED_FOREIGN_CANCEL_ACCEPTED',
    'SKYBIND_M3_DISPOSABLE_FAILED_OWNED_CANCEL',
    'SKYBIND_M3_DISPOSABLE_FAILED_CANCEL_TIMEOUT',
    'SKYBIND_M3_DISPOSABLE_FAILED_CANCEL_TERMINAL',
    'SKYBIND_M3_DISPOSABLE_FAILED_CANCEL_EVENT',
    'SKYBIND_M3_DISPOSABLE_FAILED_STALE_AFTER_CLOSE')


def parse_m3_disposable(stdout: str, *, mode: str):
    """One exact selected instrumented case; terminal outcome never inferred."""
    for marker in M3_DISPOSABLE_FAILED:
        if marker in stdout:
            return 'FAILED', marker
    for marker in M3_DISPOSABLE_BLOCKED:
        if marker in stdout:
            return 'BLOCKED', marker
    final, codes = FINAL.findall(stdout), CODES.findall(stdout)
    if '-3' in codes:
        return 'BLOCKED', 'M3_DISPOSABLE_TEST_SKIPPED'
    case, pass_state = {
        'm3-execute-live': ('liveDisposableCheckCompletes', 'PASS_M3_DISPOSABLE_CHECK_COMPLETION'),
        'm3-cancel-live': ('liveDisposableOwnedCancellation', 'PASS_M3_DISPOSABLE_OWNED_CANCEL'),
    }[mode]
    if (final == ['-1'] and codes == ['1', '0'] and
            f'INSTRUMENTATION_STATUS: test={case}' in stdout and
            'INSTRUMENTATION_STATUS: numtests=1' in stdout and
            'FAILURES!!!' not in stdout):
        return pass_state, None
    return 'FAILED', 'M3_DISPOSABLE_INSTRUMENTATION_INCOMPLETE_OR_UNCLASSIFIED'

RUNNER = TEST_APP + '/androidx.test.runner.AndroidJUnitRunner'
PATTERN = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z')
HEX = re.compile(r'[0-9a-f]{64}\Z')
SHA = re.compile(r'[0-9a-f]{40}\Z')
FINAL = re.compile(r'^INSTRUMENTATION_CODE:\s*(-?\d+)\s*$', re.M)
CODES = re.compile(r'^INSTRUMENTATION_STATUS_CODE:\s*(-?\d+)\s*$', re.M)
REMOTE_FAILURES = ('SKYBIND_LIVE_BLOCKED_ROOT_BIND',
                   'SKYBIND_LIVE_BLOCKED_ROOT_AUTH',
                   'SKYBIND_LIVE_BLOCKED_DAEMON',
                   'SKYBIND_LIVE_BLOCKED_NO_REMOTE',
                   'SKYBIND_LIVE_BLOCKED_REMOTE_NOT_CONFIGURED')
PRODUCT_FAILURES = ('SKYBIND_LIVE_FAILED_BROWSE_AUTHORIZATION',
                    'SKYBIND_LIVE_FAILED_BROWSE_VALIDATION',
                    'SKYBIND_LIVE_FAILED_BROWSE_RESPONSE',
                    'SKYBIND_LIVE_FAILED_BROWSE_TRANSPORT',
                    'SKYBIND_LIVE_FAILED_API_MISMATCH',
                    'SKYBIND_LIVE_FAILED_UNEXPECTED_LINK',
                    'SKYBIND_LIVE_FAILED_CURSOR',
                    'SKYBIND_LIVE_FAILED_BROWSE',
                    'SKYBIND_LIVE_FAILED_UNBOUNDED_BROWSE',
                    'SKYBIND_LIVE_FAILED_STALE_AFTER_CLOSE',
                    'SKYBIND_LIVE_FAILED_REBIND',
                    'SKYBIND_LIVE_FAILED_RECONNECT_SNAPSHOT')

UI_BLOCKED = ('SKYBIND_UI_NOT_REQUESTED', 'SKYBIND_UI_BLOCKED_CONNECT',
              'SKYBIND_UI_BLOCKED_NO_REMOTE', 'SKYBIND_UI_BLOCKED_REMOTE_NOT_VISIBLE',
              'SKYBIND_UI_BLOCKED_NO_FOLDER')
UI_FAILED = ('SKYBIND_UI_FAILED_INITIAL_UNPAIRED', 'SKYBIND_UI_FAILED_BROWSER_NAVIGATION',
             'SKYBIND_UI_FAILED_BROWSER_ROOT', 'SKYBIND_UI_FAILED_FOLDER_NAVIGATION',
             'SKYBIND_UI_FAILED_JOBS_ACTIVITY', 'SKYBIND_UI_FAILED_ACTIVITY_RECREATE',
             'SKYBIND_UI_FAILED_DISCONNECT_CLEANUP', 'SKYBIND_UI_FAILED_RECONNECT',
             'SKYBIND_UI_FAILED_REMOTE_SELECTION')


M3_BLOCKED = ('SKYBIND_M3_NOT_REQUESTED', 'SKYBIND_M3_BLOCKED_ROOT_BIND',
              'SKYBIND_M3_BLOCKED_DAEMON', 'SKYBIND_M3_BLOCKED_NO_ELIGIBLE_JOB',
              'SKYBIND_M3_BLOCKED_JOBS_STATUS', 'SKYBIND_M3_BLOCKED_API_MISMATCH',
              'SKYBIND_M3_BLOCKED_ROOT_AUTH')
M3_FAILED = ('SKYBIND_M3_FAILED_PREVIEW_REJECTED', 'SKYBIND_M3_FAILED_PREVIEW_IDENTITY',
             'SKYBIND_M3_FAILED_PREVIEW_CLASS', 'SKYBIND_M3_FAILED_PREVIEW_FIELDS',
             'SKYBIND_M3_FAILED_SESSION_CLEARED', 'SKYBIND_M3_FAILED_STALE_JOBS')


def parse_m3_preview(stdout):
    for marker in M3_FAILED:
        if marker in stdout:
            return 'FAILED', marker
    for marker in M3_BLOCKED:
        if marker in stdout:
            return 'BLOCKED', marker
    final, codes = FINAL.findall(stdout), CODES.findall(stdout)
    if '-3' in codes:
        return 'BLOCKED', 'M3_PREVIEW_SKIPPED'
    if (final == ['-1'] and codes == ['1', '0'] and
            'INSTRUMENTATION_STATUS: test=liveM3ReadOnlyJobPreview' in stdout and
            'INSTRUMENTATION_STATUS: numtests=1' in stdout and
            'FAILURES!!!' not in stdout):
        return 'PASS_M3_REAL_DAEMON_PREVIEW_ONLY', None
    return 'FAILED', 'M3_PREVIEW_INSTRUMENTATION_INCOMPLETE_OR_UNCLASSIFIED'


def parse_ui_live(stdout):
    """One opted-in UI test, exactly one successful terminal result; no inferred coverage."""
    final = FINAL.findall(stdout)
    codes = CODES.findall(stdout)
    if any(marker in stdout for marker in UI_BLOCKED):
        return 'BLOCKED', next(marker for marker in UI_BLOCKED if marker in stdout)
    if any(marker in stdout for marker in UI_FAILED):
        return 'FAILED', next(marker for marker in UI_FAILED if marker in stdout)
    if 'SKYBIND_UI_NOT_REQUESTED' in stdout or '-3' in codes:
        return 'BLOCKED', 'LIVE_UI_CASE_WAS_SKIPPED'
    if (final == ['-1'] and codes == ['1', '0'] and
            'INSTRUMENTATION_STATUS: test=liveUiReadOnlyNavigationRecovery' in stdout and
            'INSTRUMENTATION_STATUS: numtests=1' in stdout and
            'FAILURES!!!' not in stdout):
        return 'PASS_M2_L2_LIVE_UI_READONLY_RECOVERY', None
    return 'FAILED', 'LIVE_UI_INSTRUMENTATION_INCOMPLETE_OR_UNCLASSIFIED'


NEGATIVE_BLOCKED = ('SKYBIND_NEGATIVE_NOT_REQUESTED', 'SKYBIND_NEGATIVE_BLOCKED_ROOT_BIND',
                    'SKYBIND_NEGATIVE_BLOCKED_ROOT_AUTH', 'SKYBIND_NEGATIVE_BLOCKED_DAEMON',
                    'SKYBIND_NEGATIVE_BLOCKED_NO_REMOTE',
                    'SKYBIND_NEGATIVE_BLOCKED_REMOTE_NOT_CONFIGURED')
NEGATIVE_FAILED = ('SKYBIND_NEGATIVE_FAILED_UNSAFE_REMOTE_SELECTION',
                   'SKYBIND_NEGATIVE_FAILED_IMPLICIT_ROOT_ACCESS',
                   'SKYBIND_NEGATIVE_FAILED_STALE_UNPAIRED',
                   'SKYBIND_NEGATIVE_FAILED_API_MISMATCH',
                   'SKYBIND_NEGATIVE_FAILED_UNEXPECTED_LINK',
                   'SKYBIND_NEGATIVE_FAILED_UNSAFE_BROWSE_ACCEPTED',
                   'SKYBIND_NEGATIVE_FAILED_NEGATIVE_READ_POISONED_SESSION',
                   'SKYBIND_NEGATIVE_FAILED_TEARDOWN_NOT_UNPAIRED',
                   'SKYBIND_NEGATIVE_FAILED_TEARDOWN_LEAK')


def parse_negative_live(stdout):
    """Only one successful selected live-negative test can close this narrow gate."""
    if any(marker in stdout for marker in NEGATIVE_FAILED):
        return 'FAILED', next(s for s in NEGATIVE_FAILED if s in stdout)
    if any(marker in stdout for marker in NEGATIVE_BLOCKED):
        return 'BLOCKED', next(s for s in NEGATIVE_BLOCKED if s in stdout)
    final, codes = FINAL.findall(stdout), CODES.findall(stdout)
    if ('-3' in codes):
        return 'BLOCKED', 'NEGATIVE_LIVE_CASE_WAS_SKIPPED'
    if (final == ['-1'] and codes == ['1', '0'] and
            'INSTRUMENTATION_STATUS: test=liveReadOnlyNegativeBoundaries' in stdout and
            'INSTRUMENTATION_STATUS: numtests=1' in stdout and
            'FAILURES!!!' not in stdout):
        return 'PASS_M2_L3_READONLY_NEGATIVE_BOUNDARIES', None
    return 'FAILED', 'NEGATIVE_LIVE_INSTRUMENTATION_INCOMPLETE_OR_UNCLASSIFIED'


TRANSPORT_BLOCKED = ('SKYBIND_TRANSPORT_NOT_REQUESTED', 'SKYBIND_TRANSPORT_BLOCKED_BIND',
                     'SKYBIND_TRANSPORT_BLOCKED_ROOT_AUTH', 'SKYBIND_TRANSPORT_BLOCKED_DAEMON',
                     'SKYBIND_TRANSPORT_BLOCKED_REBIND')
TRANSPORT_FAILED = ('SKYBIND_TRANSPORT_FAILED_UNPAIRED', 'SKYBIND_TRANSPORT_FAILED_INITIAL_READ',
                    'SKYBIND_TRANSPORT_FAILED_CALLBACK_COUNT', 'SKYBIND_TRANSPORT_FAILED_DUPLICATE_CALLBACK',
                    'SKYBIND_TRANSPORT_FAILED_STALE_AUTHORITY', 'SKYBIND_TRANSPORT_FAILED_STALE_DATA',
                    'SKYBIND_TRANSPORT_FAILED_RECONNECT')


def parse_transport_live(stdout):
    for marker in TRANSPORT_FAILED:
        if marker in stdout:
            return 'FAILED', marker
    for marker in TRANSPORT_BLOCKED:
        if marker in stdout:
            return 'BLOCKED', marker
    final, codes = FINAL.findall(stdout), CODES.findall(stdout)
    if '-3' in codes:
        return 'BLOCKED', 'TRANSPORT_LIVE_CASE_SKIPPED'
    if (final == ['-1'] and codes == ['1', '0'] and
            'INSTRUMENTATION_STATUS: test=liveTransportLossAndFreshReconnect' in stdout and
            'INSTRUMENTATION_STATUS: numtests=1' in stdout and
            'FAILURES!!!' not in stdout):
        return 'PASS_M2_L3_APP_OWNED_TRANSPORT_RECOVERY', None
    return 'FAILED', 'TRANSPORT_LIVE_INCOMPLETE_OR_UNCLASSIFIED'


class Blocked(Exception):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def need(cond, reason):
    if not cond:
        raise Blocked(reason)


def invoke(argv, timeout=45, *, ok=True):
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Blocked('COMMAND_UNAVAILABLE_OR_TIMED_OUT') from exc
    if ok:
        need(p.returncode == 0, 'COMMAND_FAILED')
    return p


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for part in iter(lambda: f.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def current_source():
    sha = invoke(['git', '-C', str(ROOT), 'rev-parse', 'HEAD']).stdout.strip()
    need(SHA.fullmatch(sha), 'GIT_SOURCE_INVALID')
    need(invoke(['git', '-C', str(ROOT), 'status', '--porcelain']).stdout.strip() == '',
         'SOURCE_WORKTREE_NOT_CLEAN')
    return sha


def github(run_id, sha):
    need(shutil.which('gh') is not None, 'GH_MISSING')
    def get(route):
        response = invoke(['gh', 'api', route], timeout=35).stdout
        try:
            return json.loads(response)
        except ValueError as exc:
            raise Blocked('GITHUB_RESPONSE_INVALID') from exc
    run = get(f'repos/{REPOSITORY}/actions/runs/{run_id}')
    need(run.get('head_sha') == sha and run.get('head_branch') == 'main'
         and run.get('conclusion') == 'success' and run.get('status') == 'completed'
         and run.get('event') == 'workflow_dispatch'
         and run.get('path') == '.github/workflows/skybind-android-apks.yml',
         'REMOTE_BUILD_IDENTITY_OR_STATUS_INVALID')
    artifacts = get(f'repos/{REPOSITORY}/actions/runs/{run_id}/artifacts')
    matches = [v for v in artifacts.get('artifacts', []) if v.get('name') == ARTIFACT]
    need(len(matches) == 1, 'EXPECTED_ONE_HOSTED_PAIR_ARTIFACT')
    artifact = matches[0]
    need(not artifact.get('expired', True) and artifact.get('workflow_run', {}).get('head_sha') == sha
         and artifact.get('workflow_run', {}).get('id') == run_id
         and isinstance(artifact.get('id'), int)
         and re.fullmatch(r'sha256:[0-9a-f]{64}', artifact.get('digest', '')),
         'REMOTE_ARTIFACT_IDENTITY_INVALID')
    return artifact


def verify_candidate(directory, run_id, sha, signer):
    import apk_manifest
    paths = [directory / n for n in ('android-build-manifest.json', 'app-debug.apk',
                                     'app-debug-androidTest.apk')]
    need(all(p.is_file() and not p.is_symlink() for p in paths), 'CANDIDATE_APK_PAIR_MISSING')
    need(paths[0].stat().st_size <= 32768, 'CANDIDATE_MANIFEST_OVERSIZED')
    m = json.loads(paths[0].read_text())
    need(m.get('repository') == REPOSITORY and m.get('head_sha') == sha and
         m.get('run_id') == str(run_id) and m.get('signing') == 'persistent-github-debug'
         and m.get('signing_certificate_pin_sha256') == signer and
         m.get('release_qualified') is False and m.get('device_qualified') is False and
         m.get('app_id') == APP and m.get('test_app_id') == TEST_APP,
         'CANDIDATE_MANIFEST_IDENTITY_INVALID')
    need(all(m.get(k, {}).get('certificate_sha256') == signer for k in ('app', 'test_apk')),
         'CANDIDATE_CERTIFICATE_PIN_MISMATCH')
    args = argparse.Namespace(manifest=paths[0], app=paths[1], test_apk=paths[2],
                              expected_head_sha=sha, expected_run_id=str(run_id))
    need(apk_manifest.verify(args)['state'] == 'PASS_LOCAL_HASH_AND_CERT',
         'CANDIDATE_APK_SIGNATURE_OR_HASH_INVALID')
    return m


def choose_device(serial):
    need(shutil.which('adb') is not None, 'ADB_MISSING')
    rows = invoke(['adb', 'devices']).stdout.splitlines()[1:]
    ready = [cells[0] for line in rows if (cells := line.split()) and len(cells) == 2
             and cells[1] == 'device']
    need(len(set(ready)) == len(ready), 'DUPLICATE_DEVICE_RECORD')
    if serial:
        need(serial in ready, 'SELECTED_DEVICE_NOT_AUTHORIZED')
        return serial
    need(len(ready) == 1, 'REQUIRE_EXACTLY_ONE_ADB_DEVICE_OR_SERIAL')
    return ready[0]


def adb(serial, *args, timeout=45, ok=True):
    return invoke(['adb', '-s', serial, *args], timeout=timeout, ok=ok)


def installed_pair(serial, manifest, signer):
    import apk_manifest
    with tempfile.TemporaryDirectory(prefix='skybind-m2-live-check-') as tmp:
        for package, name, key in ((APP, 'app-debug.apk', 'app'),
                                   (TEST_APP, 'app-debug-androidTest.apk', 'test_apk')):
            info = adb(serial, 'shell', 'pm', 'path', package, ok=False)
            paths = [v.removeprefix('package:').strip() for v in info.stdout.splitlines()
                     if v.startswith('package:')]
            need(info.returncode == 0 and len(paths) == 1 and
                 paths[0].startswith('/data/app/') and paths[0].endswith('/base.apk') and
                 re.fullmatch(r'[A-Za-z0-9_./+@=:\-~]+', paths[0]) is not None,
                 'INSTALLED_PACKAGE_ABSENT_SPLIT_OR_UNTRUSTED')
            dst = Path(tmp) / name
            adb(serial, 'pull', paths[0], str(dst), timeout=90)
            need(sha256(dst) == manifest[key]['sha256'], 'INSTALLED_APK_PAIR_DIFFERS_FROM_HOSTED')
            need(apk_manifest.apk_cert(dst) == signer, 'INSTALLED_SIGNER_PIN_MISMATCH')
    return True


def parse_live(stdout):
    """One specifically selected case, no skip, exactly one pass, final success."""
    final = FINAL.findall(stdout)
    codes = CODES.findall(stdout)
    if (final == ['-1'] and codes == ['1', '0'] and
            'INSTRUMENTATION_STATUS: test=liveReadBrowseAndReconnect' in stdout and
            'INSTRUMENTATION_STATUS: numtests=1' in stdout and
            'FAILURES!!!' not in stdout and 'SKYBIND_LIVE_NOT_REQUESTED' not in stdout):
        return ('PASS_M2_L1_LIVE_READ_BROWSE_REBIND', None)
    for reason in REMOTE_FAILURES:
        if reason in stdout:
            return ('BLOCKED', reason)
    for reason in PRODUCT_FAILURES:
        if reason in stdout:
            return ('FAILED', reason)
    if 'SKYBIND_LIVE_NOT_REQUESTED' in stdout or '-3' in codes:
        return ('BLOCKED', 'LIVE_CASE_WAS_SKIPPED')
    return ('FAILED', 'INSTRUMENTATION_INCOMPLETE_OR_UNCLASSIFIED')


def store(report, *, dest=None):
    folder = dest or (Path.home() / '.local/state/skybind/native-m2-live')
    need(not folder.is_symlink(), 'RECEIPT_DIRECTORY_SYMLINK')
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    filename = folder / ('m2-live-' + uuid.uuid4().hex + '.json')
    # The saved evidence and emitted summary MUST identify the same immutable file.
    # Otherwise the outer CI lane launcher rejects even an otherwise valid result.
    report['receipt'] = str(filename)
    with filename.open('x', encoding='utf-8') as f:
        json.dump(report, f, sort_keys=True, indent=2)
        f.write('\n')
    filename.chmod(0o600)
    return str(filename)


def run(opts):
    doc = dict(schema='skybind-m2-live-v1', state='BLOCKED', reason=None,
               source_sha=None, github_run_id=opts.run_id,
               artifact_id=None, artifact_digest=None, device_qualified=False,
               m2_l1_device_qualified=False, m2_l2_device_qualified=False,
               release_qualified=False, github_run_authenticated=False,
               remote_metadata_verified=False, signing_verified=False,
               installed_pair_verified=False, installed_apks_modified=False,
               root_grant_changed_by_runner=False, daemon_mutated=False,
               remote_selection='explicit' if opts.remote else 'first_configured',
               mode=opts.mode, m2_l3_negative_device_qualified=False,
               m2_l3_transport_device_qualified=False,
               m3_preview_device_qualified=False, m3_execute_device_qualified=False,
               m3_cancel_device_qualified=False, m3_copy_device_qualified=False, tests={}, recorded_at_utc=datetime.now(timezone.utc).isoformat())
    try:
        need(isinstance(opts.run_id, int) and opts.run_id > 0, 'RUN_ID_INVALID')
        if opts.mode == 'm3-execute-live':
            need(getattr(opts, 'allow_disposable_job_execution', False),
                 'M3_DISPOSABLE_EXECUTION_EXPLICIT_AUTHORIZATION_REQUIRED')
        if opts.mode == 'm3-cancel-live':
            need(getattr(opts, 'allow_disposable_job_execution', False) and
                 getattr(opts, 'allow_disposable_job_cancellation', False),
                 'M3_DISPOSABLE_CANCEL_EXPLICIT_AUTHORIZATION_REQUIRED')
        if opts.mode == 'm3-copy-live':
            need(getattr(opts,'allow_disposable_job_execution',False) and
                 getattr(opts,'allow_disposable_copy_writes',False),
                 'M3_COPY_WRITES_EXPLICIT_AUTHORIZATION_REQUIRED')
        if opts.remote is not None:
            need(PATTERN.fullmatch(opts.remote), 'REMOTE_NAME_INVALID')
        sha = current_source()
        doc['source_sha'] = sha
        artifact = github(opts.run_id, sha)
        doc['remote_metadata_verified'] = True
        doc['artifact_id'] = artifact['id']
        doc['artifact_digest'] = artifact['digest']
        folder = opts.artifact_dir or (Path.home()/'.cache/skybind'/f'hosted-{opts.run_id}')
        manifest = verify_candidate(folder, opts.run_id, sha,
                                    read_pin())
        doc['signing_verified'] = True
        doc['app_sha256'] = manifest['app']['sha256']
        doc['test_sha256'] = manifest['test_apk']['sha256']
        device = choose_device(opts.serial)
        doc['device_serial_sha256'] = hashlib.sha256(device.encode()).hexdigest()
        api = adb(device, 'shell', 'getprop', 'ro.build.version.sdk').stdout.strip()
        need(api.isdecimal() and int(api) >= 28, 'DEVICE_ANDROID_API_UNSUPPORTED')
        doc['device_api'] = int(api)
        need(adb(device, 'shell', 'getenforce').stdout.strip() == 'Enforcing',
             'DEVICE_SELINUX_NOT_ENFORCING')
        installed_pair(device, manifest, read_pin())
        doc['installed_pair_verified'] = True
        if opts.mode == 'm3-copy-live':
            import m3_copy_fixture as copy_fixture
            try:
                reg, registered = copy_fixture.registry()
                need(registered, 'M3_COPY_FIXTURE_UNREGISTERED')
                doc['copy_preflight'] = copy_fixture.fixture_state('prepared')
            except copy_fixture.Blocked as exc:
                raise Blocked('M3_COPY_FIXTURE_PREFLIGHT:'+str(exc)[:64]) from exc
            doc['copy_fixture_registered'] = True
        if opts.mode == 'preflight':
            doc['state'] = 'PASS_M2_L1_PAIR_PREFLIGHT_ONLY'
        else:
            ui_mode = opts.mode == 'ui-live'
            negative_mode = opts.mode == 'negative-live'
            transport_mode = opts.mode == 'transport-live'
            m3_mode = opts.mode == 'm3-preview-live'
            m3_execute = opts.mode == 'm3-execute-live'
            m3_cancel = opts.mode == 'm3-cancel-live'
            m3_copy = opts.mode == 'm3-copy-live'
            if ui_mode:
                args = ['shell', 'am', 'instrument', '-w', '-r',
                        '-e', 'skybind.ui.live', 'true', '-e', 'class', UI_CASE]
            elif negative_mode:
                args = ['shell', 'am', 'instrument', '-w', '-r',
                        '-e', 'skybind.negative.live', 'true', '-e', 'class', NEGATIVE_CASE]
            elif m3_mode:
                args = ['shell', 'am', 'instrument', '-w', '-r',
                        '-e', 'skybind.m3.preview.live', 'true', '-e', 'class', M3_CASE]
            elif m3_copy:
                args = ['shell','am','instrument','-w','-r',
                        '-e','skybind.m3.copy.live','true','-e','class',M3_COPY_CASE]
            elif m3_execute or m3_cancel:
                args = ['shell', 'am', 'instrument', '-w', '-r',
                        '-e', ('skybind.m3.execute.live' if m3_execute else 'skybind.m3.cancel.live'),
                        'true', '-e', 'class', (M3_EXECUTE_CASE if m3_execute else M3_CANCEL_CASE)]
            elif transport_mode:
                args = ['shell', 'am', 'instrument', '-w', '-r',
                        '-e', 'skybind.transport.live', 'true', '-e', 'class', TRANSPORT_CASE]
            else:
                args = ['shell', 'am', 'instrument', '-w', '-r',
                        '-e', 'skybind.live', 'true', '-e', 'class', CASE]
            if opts.remote:
                args += ['-e', 'skybind.remote', opts.remote]
            args.append(RUNNER)
            outcome = adb(device, *args, timeout=300 if (ui_mode or m3_execute or m3_cancel or m3_copy) else 190, ok=False)
            state, reason = (parse_ui_live(outcome.stdout) if ui_mode else
                             parse_negative_live(outcome.stdout) if negative_mode else
                             parse_transport_live(outcome.stdout) if transport_mode else
                             parse_m3_preview(outcome.stdout) if m3_mode else
                             parse_m3_disposable(outcome.stdout, mode=opts.mode) if (m3_execute or m3_cancel) else
                             parse_m3_copy(outcome.stdout) if m3_copy else
                             parse_live(outcome.stdout))
            doc['state'], doc['reason'] = state, reason
            case_name = ('liveUiReadOnlyNavigationRecovery' if ui_mode else
                         'liveReadOnlyNegativeBoundaries' if negative_mode else
                         'liveTransportLossAndFreshReconnect' if transport_mode else
                         'liveM3ReadOnlyJobPreview' if m3_mode else
                         'liveDisposableCheckCompletes' if m3_execute else
                         'liveDisposableOwnedCancellation' if m3_cancel else
                         'liveDisposableCopyReconnectReconcile' if m3_copy else
                         'liveReadBrowseAndReconnect')
            doc['tests'][case_name] = state
            doc['instrumentation_process_exit_zero'] = outcome.returncode == 0
            if state.startswith('PASS_'):
                need(outcome.returncode == 0, 'INSTRUMENTATION_PROCESS_NONZERO')
                if ui_mode:
                    doc['m2_l2_device_qualified'] = True  # UI gate only, NOT real daemon death
                    doc['qualified_scope'] = 'M2-L2_REAL_COMPOSE_UI_BROWSE_DISCONNECT_RECONNECT'
                elif negative_mode:
                    doc['m2_l3_negative_device_qualified'] = True
                    doc['qualified_scope'] = 'M2-L3_READONLY_NEGATIVE_BOUNDARIES_ONLY'
                elif m3_mode:
                    doc['m3_preview_device_qualified'] = True
                    doc['qualified_scope'] = 'M3_REAL_DAEMON_JOB_PREVIEW_ONLY_NO_EXECUTION'
                elif m3_execute:
                    doc['m3_execute_device_qualified'] = True
                    doc['qualified_scope'] = 'M3_DISPOSABLE_CHECK_START_TO_TERMINAL_EVENTS_ONLY'
                elif m3_copy:
                    try:
                        doc['copy_integrity'] = copy_fixture.fixture_state('complete')
                        need(doc['copy_integrity']['expected_content_sha256'] ==
                             doc['copy_preflight']['expected_content_sha256'],
                             'M3_COPY_SOURCE_INTEGRITY_DRIFT')
                    except (copy_fixture.Blocked,OSError,ValueError,KeyError,TypeError):
                        doc['state']='FAILED'
                        doc['reason']='SKYBIND_M3_COPY_FAILED_DESTINATION_INTEGRITY'
                    else:
                        doc['m3_copy_device_qualified']=True
                        doc['qualified_scope']='M3_LOCAL_DISPOSABLE_COPY_SHA256_RECONNECT_TERMINAL_ONLY'
                elif m3_cancel:
                    doc['m3_cancel_device_qualified'] = True
                    doc['qualified_scope'] = 'M3_DISPOSABLE_SESSION_OWNED_CANCEL_ONLY'
                elif transport_mode:
                    doc['m2_l3_transport_device_qualified'] = True
                    doc['qualified_scope'] = 'M2-L3_APP_OWNED_TRANSPORT_LOSS_RECOVERY_ONLY'
                else:
                    doc['m2_l1_device_qualified'] = True  # Narrow gate only
                    doc['qualified_scope'] = 'M2-L1_READ_ONLY_APP_ROOTSERVICE_QUERY_BROWSE_REBIND'
    except (Blocked, OSError, ValueError, KeyError, TypeError,
            json.JSONDecodeError) as exc:
        doc['reason'] = exc.reason if isinstance(exc, Blocked) else type(exc).__name__.upper()
        doc['state'] = 'BLOCKED'
    doc['receipt'] = store(doc)
    print(json.dumps({k: doc.get(k) for k in ('state', 'reason', 'receipt', 'source_sha',
          'github_run_id', 'artifact_id', 'device_api', 'installed_pair_verified',
          'device_qualified', 'm2_l1_device_qualified', 'm2_l2_device_qualified',
          'm2_l3_negative_device_qualified', 'm2_l3_transport_device_qualified',
          'm3_preview_device_qualified', 'm3_execute_device_qualified',
          'm3_cancel_device_qualified','m3_copy_device_qualified')}, sort_keys=True))
    return 0 if doc['state'].startswith('PASS_') else 2


def read_pin():
    path = Path.home() / '.local/share/skybind/signing/signer-sha256.txt'
    need(path.is_file() and not path.is_symlink() and path.stat().st_size <= 128,
         'LOCAL_SIGNER_PIN_MISSING')
    value = path.read_text('ascii').strip()
    need(HEX.fullmatch(value), 'LOCAL_SIGNER_PIN_INVALID')
    return value


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-id', type=int, required=True, help='Current exact-source GitHub APK build')
    p.add_argument('--mode', choices=('preflight','live','ui-live','negative-live','transport-live','m3-preview-live','m3-execute-live','m3-cancel-live'), default='preflight')
    p.add_argument('--allow-disposable-job-execution', action='store_true',
                   help='Explicitly opt into test-owned manual-only CHECK job launch')
    p.add_argument('--allow-disposable-job-cancellation', action='store_true',
                   help='Explicitly opt into cancellation of the test-owned run only')
    p.add_argument('--remote', help='Optional configured remote; otherwise first sorted daemon remote')
    p.add_argument('--serial', help='ADB serial if more than one device is connected')
    p.add_argument('--artifact-dir', type=Path, help='Local gh-downloaded exact-run APK pair')
    return run(p.parse_args())

if __name__ == '__main__':
    raise SystemExit(main())
