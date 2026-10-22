#!/usr/bin/env python3
"""One-admission, opt-in M2/M3 Android instrumentation recheck.

A read-only five-case batch is default. A full nine-case batch requires
separate explicit authorizations for disposable CHECK, cancel, COPY writes
and an app-only force-stop/cold-launch.
The runner never installs/uninstalls packages or prepares/removes fixtures.
All results come from the already-installed, exact-hosted Skybind APK pair.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

import m2_live_device as live

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = 'skybind-m2-m3-fresh-batch-v1'
LANES = {
    'live': (live.CASE, 'skybind.live', live.parse_live,
             'm2_l1_device_qualified'),
    'ui-live': (live.UI_CASE, 'skybind.ui.live', live.parse_ui_live,
                'm2_l2_device_qualified'),
    'negative-live': (live.NEGATIVE_CASE, 'skybind.negative.live', live.parse_negative_live,
                      'm2_l3_negative_device_qualified'),
    'transport-live': (live.TRANSPORT_CASE, 'skybind.transport.live', live.parse_transport_live,
                       'm2_l3_transport_device_qualified'),
    'm3-preview-live': (live.M3_CASE, 'skybind.m3.preview.live', live.parse_m3_preview,
                        'm3_preview_device_qualified'),
    'm3-execute-live': (live.M3_EXECUTE_CASE, 'skybind.m3.execute.live', None,
                        'm3_execute_device_qualified'),
    'm3-cancel-live': (live.M3_CANCEL_CASE, 'skybind.m3.cancel.live', None,
                       'm3_cancel_device_qualified'),
    'm3-copy-live': (live.M3_COPY_CASE, 'skybind.m3.copy.live', live.parse_m3_copy,
                     'm3_copy_device_qualified'),
    'm2-process-live': (None, None, None, 'm2_l3_process_device_qualified'),
}
READONLY = tuple(LANES)[:5]
FULL = tuple(LANES)
FLAGS = [LANES[mode][3] for mode in FULL]
STATUS_MARK = re.compile(r'^INSTRUMENTATION_STATUS_CODE:\s*(-?\d+)\s*$', re.M)
FINAL_MARK = re.compile(r'^INSTRUMENTATION_CODE:\s*(-?\d+)\s*$', re.M)


class BatchBlocked(Exception):
    pass


def plan(profile: str, *, check: bool, cancel: bool, copy: bool, stop: bool) -> tuple[str, ...]:
    if profile == 'readonly':
        if check or cancel or copy or stop:
            raise BatchBlocked('DISPOSABLE_AUTHORIZATION_WITH_READONLY_PROFILE')
        return READONLY
    if profile != 'full' or not (check and cancel and copy and stop):
        raise BatchBlocked('FULL_REQUIRES_CHECK_CANCEL_COPY_AND_APP_FORCE_STOP_AUTHORIZATION')
    return FULL


def classify(mode: str, stdout: str, exitcode: int) -> tuple[str, str | None]:
    if mode == 'm2-process-live':
        raise ValueError('process lane has a separate device-process verifier')
    parser = LANES[mode][2]
    state, reason = (live.parse_m3_disposable(stdout, mode=mode) if parser is None else parser(stdout))
    # Android am may report INSTRUMENTATION_CODE -1 even on a failed test.
    if state.startswith('PASS_') and (exitcode != 0 or 'FAILURES!!!' in stdout or
       '-2' in STATUS_MARK.findall(stdout) or FINAL_MARK.findall(stdout) != ['-1'] or
       stdout.count('OK (1 test)') != 1):
        return 'FAILED', 'INSTRUMENTATION_TERMINAL_CONTRADICTION'
    return state, reason


def check_fixture(profile: str, serial: str):
    """Use the admitted ADB target, NEVER the invoking Termux filesystem.

    Full profile has two explicitly operator-prepared, non-SYNC test fixtures.
    No mutation is made by this preflight. Exact target files are hashed.
    """
    if profile != 'full':
        return None
    import m3_adb_fixture
    try:
        registry, _runs = m3_adb_fixture.registry(serial)
        jobs = registry['jobs']
        if not any(j.get('name') == 'M3DisposableCheck' for j in jobs):
            raise BatchBlocked('TARGET_CHECK_FIXTURE_NOT_REGISTERED')
        if not any(j.get('name') == 'M3DisposableCopy' for j in jobs):
            raise BatchBlocked('TARGET_COPY_FIXTURE_NOT_REGISTERED')
        m3_adb_fixture.verify(serial, 'check', 'prepared')
        pre = m3_adb_fixture.verify(serial, 'copy', 'prepared')
    except (m3_adb_fixture.Blocked, ValueError, OSError, KeyError, TypeError) as e:
        raise BatchBlocked('TARGET_TEST_OWNED_FIXTURE_NOT_READY') from e
    return pre


# Exact five-file, Android-free source delta admitted only by explicit choice.
# Keep these postimages tied to the shipped and locally tested repair overlay.
SOURCE_ONLY_DELTA = {
    'docs/devtool/DEVTOOL_IMPROVEMENTS_CUMULATIVE_B1C_20261017.md': 'M',
    'scripts/dev/android/m2_m3_retest_batch.py': 'M',
    'scripts/dev/android/m3_adb_fixture.py': 'A',
    'tests/test_m2_m3_retest_batch.py': 'M',
    'tests/test_m3_adb_fixture.py': 'A',
}
# Filled by bundle finalization. All postimages must match reviewed bytes.
SOURCE_ONLY_POSTIMAGES = {  # SOURCE_ONLY_LOCK
    'docs/devtool/DEVTOOL_IMPROVEMENTS_CUMULATIVE_B1C_20261017.md': '7996de8f8f10c69cc2e0418a5580cab7c49597b0a06b1b6f8178d02502b59b13',
    'scripts/dev/android/m3_adb_fixture.py': '415157bff88d48932fc439ad9b5aa1323851e6804b89ef63963c2f5f0461eed0',
    'tests/test_m2_m3_retest_batch.py': '1ab2c1b4ca8d23f75213fd9500afa9376294b5ba4036098b558abeb455b811c8',
    'tests/test_m3_adb_fixture.py': 'a5b06ff2923cfb0db955cb55573c7b745454f52e9ec953da747e2dcc56c57b06',
}


def admitted_source(opts):
    current = live.current_source()
    approved = getattr(opts, 'apk_source_sha', None)
    if not approved or approved == current:
        return current, current, []
    if not re.fullmatch('[0-9a-f]{40}',approved):
        raise BatchBlocked('APK_SOURCE_PIN_INVALID')
    def git(*args):
        try:
            r = subprocess.run(['git','-C',str(ROOT),*args],capture_output=True,
                               text=True,timeout=20,check=False)
        except (OSError,subprocess.TimeoutExpired) as exc:
            raise BatchBlocked('GIT_DELTA_VERIFICATION_UNAVAILABLE') from exc
        if r.returncode:
            raise BatchBlocked('GIT_DELTA_VERIFICATION_FAILED')
        return r.stdout.strip()
    if git('status','--porcelain','--untracked-files=normal'):
        raise BatchBlocked('GIT_DIRTY_RUNNER_TREE')
    git('merge-base','--is-ancestor',approved,current)
    raw=git('diff','--name-status','--no-renames',approved,current)
    rows={}
    for line in raw.splitlines():
        parts=line.split('\t')
        if len(parts)!=2 or parts[1] in rows or parts[0] not in ('A','M'):
            raise BatchBlocked('UNREVIEWED_RUNNER_SOURCE_DELTA')
        rows[parts[1]]=parts[0]
    if rows!=SOURCE_ONLY_DELTA:
        raise BatchBlocked('UNREVIEWED_RUNNER_SOURCE_DELTA')
    for path, sha in SOURCE_ONLY_POSTIMAGES.items():
        p=ROOT/path
        if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=sha:
            raise BatchBlocked('REVIEWED_RUNNER_FILE_DRIFT')
    if set(SOURCE_ONLY_POSTIMAGES)!=set(SOURCE_ONLY_DELTA)-{'scripts/dev/android/m2_m3_retest_batch.py'}:
        raise BatchBlocked('REVIEWED_RUNNER_POSTIMAGE_INCOMPLETE')
    return approved,current,list(SOURCE_ONLY_DELTA)


def install_readonly_guard(opts, doc):
    # No installation is ever attempted by this runner.
    sha, runner_sha, delta = admitted_source(opts)
    doc['source_sha'] = sha
    doc['runner_source_sha'] = runner_sha
    doc['reviewed_host_tooling_delta'] = delta
    artifact = live.github(opts.run_id, sha)
    doc['artifact_id'] = artifact['id']
    doc['artifact_digest'] = artifact['digest']
    folder = opts.artifact_dir or Path.home()/'.cache/skybind'/f'hosted-{opts.run_id}'
    pin = live.read_pin()
    manifest = live.verify_candidate(folder, opts.run_id, sha, pin)
    doc['apk_hashes'] = {key: manifest[key]['sha256'] for key in ('app','test_apk')}
    doc['signer_sha256'] = pin
    serial = live.choose_device(opts.serial)
    doc['device_serial_sha256'] = hashlib.sha256(serial.encode()).hexdigest()
    sdk = live.adb(serial, 'shell','getprop','ro.build.version.sdk').stdout.strip()
    live.need(sdk.isdecimal() and int(sdk) >= 28, 'DEVICE_ANDROID_API_UNSUPPORTED')
    doc['device_api'] = int(sdk)
    live.need(live.adb(serial,'shell','getenforce').stdout.strip()=='Enforcing','SELINUX_NOT_ENFORCING')
    live.installed_pair(serial, manifest, pin)
    doc['installed_pair_verified'] = True
    return serial


def write_receipt(doc, dest: Path | None):
    folder = dest or Path.home()/'.local/state/skybind/m2-m3-retests'
    if folder.is_symlink():
        raise BatchBlocked('RECEIPT_DIRECTORY_IS_SYMLINK')
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    if folder.stat().st_mode & 0o077:
        raise BatchBlocked('RECEIPT_DIRECTORY_PERMISSIONS_UNSAFE')
    path = folder/f'm2m3-{uuid.uuid4().hex}.json'
    doc['receipt'] = str(path)
    with path.open('x', encoding='utf-8') as f:
        json.dump(doc, f, sort_keys=True, indent=2)
        f.write('\n')
    path.chmod(0o600)
    return path


def run(opts):
    report = {
        'schema': SCHEMA, 'state': 'BLOCKED', 'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
        'source_sha': None, 'github_run_id': opts.run_id, 'artifact_id': None,
        'remote': opts.remote, 'profile': opts.profile,
        'requested_modes': [], 'cases': {}, 'blocked_reason': None,
        'installed_pair_verified': False,
        'm2_m3_device_retests_run': False, 'external_provider_qualified': False,
        'whole_m3_qualified': False, 'release_qualified': False,
        'installed_apks_modified': False, 'root_grant_changed_by_runner': False,
        'fixture_created_or_removed_by_runner': False,
        'app_force_stop_attempted': False, 'app_force_stop_performed': False,
        'disposable_authorizations': {
            'check': opts.allow_disposable_job_execution,
            'cancel': opts.allow_disposable_job_cancellation,
            'copy': opts.allow_disposable_copy_writes,
            'app_force_stop': opts.allow_app_force_stop,
        },
    }
    for flag in FLAGS:
        report[flag] = False
    try:
        modes = plan(opts.profile, check=opts.allow_disposable_job_execution,
                     cancel=opts.allow_disposable_job_cancellation,
                     copy=opts.allow_disposable_copy_writes,
                     stop=opts.allow_app_force_stop)
        report['requested_modes'] = list(modes)
        if opts.remote is not None and not live.PATTERN.fullmatch(opts.remote):
            raise BatchBlocked('REMOTE_NAME_INVALID')
        if opts.run_id <= 0:
            raise BatchBlocked('GITHUB_RUN_ID_INVALID')
        serial = install_readonly_guard(opts, report)
        copy_pre = check_fixture(opts.profile, serial)
        if copy_pre is not None:
            report['copy_preflight'] = copy_pre
        for mode in modes:
            case, switch, _parser, flag = LANES[mode]
            start = time.monotonic()
            if mode == 'm2-process-live':
                import m2_process_live
                try:
                    observation = m2_process_live.verify_app_cold_launch(
                        serial, approved=True,
                        mark_force_stop=lambda: report.update(app_force_stop_attempted=True),
                        mark_done=lambda: report.update(app_force_stop_performed=True))
                    if observation.get('cold_ui_observed') is not True or observation.get('new_process_observed') is not True:
                        raise BatchBlocked('COLD_APP_LIFECYCLE_EVIDENCE_INCOMPLETE')
                    report['m2_process_observation'] = observation
                    state,reason='PASS_M2_L3_APP_PROCESS_COLD_LAUNCH',None
                except (BatchBlocked, live.Blocked, OSError, ValueError):
                    state,reason='BLOCKED','M2_PROCESS_COLD_LAUNCH_NOT_QUALIFIED'
            else:
                args = ['shell','am','instrument','-w','-r','-e',switch,'true','-e','class',case]
                if opts.remote:
                    args += ['-e','skybind.remote',opts.remote]
                args.append(live.RUNNER)
                try:
                    outcome = live.adb(serial,*args,timeout=300 if mode in ('ui-live','m3-execute-live','m3-cancel-live','m3-copy-live') else 190,ok=False)
                    state, reason = classify(mode, outcome.stdout, outcome.returncode)
                except live.Blocked:
                    state,reason='BLOCKED','INSTRUMENTATION_TRANSPORT_UNAVAILABLE'
                except (OSError,subprocess.TimeoutExpired):
                    state,reason='BLOCKED','INSTRUMENTATION_TIMEOUT_OR_UNAVAILABLE'
            if mode == 'm3-copy-live' and state.startswith('PASS_'):
                import m3_adb_fixture
                try:
                    after = m3_adb_fixture.verify(serial,'copy','complete')
                    if after['expected_content_sha256'] != copy_pre['expected_content_sha256']:
                        raise BatchBlocked('COPY_SOURCE_INTEGRITY_DRIFT')
                    report['copy_integrity'] = after
                except (m3_adb_fixture.Blocked, BatchBlocked, OSError, ValueError, KeyError):
                    state,reason='FAILED','COPY_DESTINATION_INTEGRITY_NOT_VERIFIED'
            report['cases'][mode] = {'state': state, 'reason': reason,
                                      'elapsed_ms': int((time.monotonic()-start)*1000),
                                      'qualified_scope': flag}
            report[flag] = state.startswith('PASS_')
            print(f'R1_M2_M3_LANE mode={mode} state={state} reason={reason or "none"}', flush=True)
            if not state.startswith('PASS_'):
                report['state'] = 'BLOCKED_M2_M3_BATCH_INCOMPLETE'
                report['blocked_reason'] = 'LANE_NOT_PASS:' + mode
                break
        else:
            if modes == FULL and all(report[f] for f in FLAGS):
                report['m2_m3_device_retests_run'] = True
                report['state'] = 'PASS_M2_M3_FRESH_NINE_LANE_AUTOMATED_RETEST_ONLY'
            else:
                report['state'] = 'PASS_M2_M3_FRESH_READONLY_FIVE_LANE_ONLY'
    except (BatchBlocked, live.Blocked) as e:
        report['blocked_reason'] = str(e)[:110]
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError, subprocess.TimeoutExpired) as e:
        report['blocked_reason'] = 'PREFLIGHT_' + type(e).__name__.upper()
    try:
        write_receipt(report, opts.output_dir)
    except (BatchBlocked, OSError) as e:
        print('R1_M2_M3_RECEIPT_UNAVAILABLE '+type(e).__name__,file=sys.stderr)
        return 2
    print(json.dumps({'state':report['state'], 'receipt':report['receipt'],
                      'm2_m3_device_retests_run':report['m2_m3_device_retests_run'],
                      'passed':sum(v['state'].startswith('PASS_') for v in report['cases'].values()),
                      'requested':len(report['requested_modes']),
                      'blocked_reason':report['blocked_reason'],
                      'external_provider_qualified':False, 'release_qualified':False},sort_keys=True))
    return 0 if report['state'].startswith('PASS_') else 2


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-id', type=int, required=True)
    p.add_argument('--remote', help='Exact configured remote (e.g. GDDavys)')
    p.add_argument('--serial', help='ADB device serial, required for multiple devices')
    p.add_argument('--artifact-dir',type=Path,help='Pre-downloaded exact GitHub app+test APK pair')
    p.add_argument('--apk-source-sha',help='Explicit hosted APK source when the reviewed host-only tool delta is committed')
    p.add_argument('--output-dir',type=Path)
    p.add_argument('--profile',choices=('readonly','full'),default='readonly')
    p.add_argument('--allow-disposable-job-execution',action='store_true')
    p.add_argument('--allow-disposable-job-cancellation',action='store_true')
    p.add_argument('--allow-disposable-copy-writes',action='store_true')
    p.add_argument('--allow-app-force-stop', action='store_true',
                   help='Explicitly authorize app-only force-stop/cold-launch; never stops daemon')
    return run(p.parse_args(argv))


if __name__=='__main__':
    raise SystemExit(main())
