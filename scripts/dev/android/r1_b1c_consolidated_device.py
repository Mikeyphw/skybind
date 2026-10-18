#!/usr/bin/env python3
"""B1-C4..C7: device qualification of a NEW, explicitly attested source-bound APK pair.

No implicit GitHub dispatch, installation, replacement, uninstall, data clear, root,
or privileged broker enablement. Historical H4 B1-C receipts are never rewritten.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import uuid

import r1_b1c_device as b1c
import r1_b1c3_identity as identity_survey

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / 'build/evidence/android/b1c-consolidated'
CASES = {
    ('io.github.mikeyphw.skybind.ScaffoldTest', 'appStartsWithoutBrokerOrRoot'),
    ('io.github.mikeyphw.skybind.UidPackageEvidenceTest', 'deniesUnknownOrUnpinnedCaller'),
    ('io.github.mikeyphw.skybind.BinderCallerGateTest', 'signedPackageOwnershipHasPositiveAndNegativeEvidence'),
    ('io.github.mikeyphw.skybind.BinderCallerGateTest', 'binderCallerGateDefaultsToDenyAndRequiresExactOperatorPin'),
}


def current_source_sha():
    result = subprocess.run(['git', 'rev-parse', '--verify', 'HEAD'], cwd=ROOT,
                            capture_output=True, text=True, timeout=10)
    b1c.need(result.returncode == 0 and b1c.HEX64.fullmatch(result.stdout.strip()) is not None,
             'LOCAL_GIT_SOURCE_UNVERIFIABLE')
    for flag in (['git', 'diff', '--quiet', '--exit-code'],
                 ['git', 'diff', '--cached', '--quiet', '--exit-code']):
        check = subprocess.run(flag, cwd=ROOT, capture_output=True, timeout=10)
        b1c.need(check.returncode == 0, 'LOCAL_SOURCE_TRACKED_DRIFT')
    return result.stdout.strip()


def verified_new_attestation(pipeline_id: str, sha: str) -> dict:
    b1c.need(re.fullmatch('[0-9a-f]{32}', pipeline_id) is not None, 'PIPELINE_ID_INVALID')
    path = ROOT / 'build/evidence/r1-android-hosted' / pipeline_id / 'attestation.json'
    b1c.need(path.is_file() and not path.is_symlink() and path.stat().st_size <= 16384,
             'NEW_SOURCE_ATTESTATION_MISSING')
    receipt = json.loads(path.read_text())
    required = {
        'status': 'PASS_HOSTED_PAIR_INSPECTED_NOT_DEVICE_QUALIFIED',
        'repository': 'Mikeyphw/skybind',
        'head_sha': sha, 'device_qualified': False,
        'release_qualified': False, 'github_run_authenticated': True,
        'signatures_inspected': True,
    }
    for k, value in required.items():
        b1c.need(type(receipt.get(k)) is type(value) and receipt.get(k) == value,
                 'NEW_ATTESTATION_' + k.upper() + '_INVALID')
    for field in ('app_sha256', 'test_sha256', 'artifact_zip_sha256', 'debug_signer_sha256'):
        b1c.need(isinstance(receipt.get(field), str) and b1c.HEX64.fullmatch(receipt[field]),
                 'NEW_ATTESTATION_HASH_INVALID')
    for field in ('run_id','run_attempt','artifact_id'):
        b1c.need(type(receipt.get(field)) is int and receipt[field] > 0,
                 'NEW_ATTESTATION_REMOTE_ID_INVALID')
    b1c.need(pipeline_id != b1c.PIPELINE and sha != b1c.SOURCE,
             'LEGACY_PAIR_CANNOT_SATISFY_CONSOLIDATED_TESTS')
    return receipt


def parse_four_cases(stdout: str) -> dict:
    pending = {}
    found = {}
    for raw in stdout.replace('\r', '').splitlines():
        if raw.startswith('INSTRUMENTATION_STATUS: '):
            field = raw[len('INSTRUMENTATION_STATUS: '):]
            if '=' in field:
                key, val = field.split('=', 1)
                if key in ('class', 'test'):
                    pending[key] = val.strip()
        elif raw.startswith('INSTRUMENTATION_STATUS_CODE: '):
            raw_code = raw.split(':', 1)[1].strip()
            b1c.need(re.fullmatch(r'-?\d+', raw_code) is not None, 'MALFORMED_INSTRUMENTATION_STATUS')
            code = int(raw_code)
            if code == 0:
                key = (pending.get('class'), pending.get('test'))
                b1c.need(key in CASES and key not in found, 'UNEXPECTED_OR_DUPLICATE_INSTRUMENTATION_CASE')
                found[key] = 'PASS'
            elif code != 1:
                raise b1c.Blocked('INSTRUMENTATION_CASE_FAILED')
            pending = {}
    b1c.need(re.findall(r'^INSTRUMENTATION_CODE:\s*(-?\d+)\s*$', stdout, flags=re.M) == ['-1'],
             'INSTRUMENTATION_FINAL_STATUS_INVALID')
    b1c.need(set(found) == CASES, 'INSTRUMENTATION_CASES_INCOMPLETE')
    b1c.need('INSTRUMENTATION_FAILED' not in stdout and 'FAILURES!!!' not in stdout,
             'INSTRUMENTATION_ERROR_MARKER')
    return {f'{cl.rsplit(".", 1)[-1]}#{fn}': 'PASS' for cl, fn in sorted(found)}


def write_once(report):
    b1c.need(not OUTPUT.is_symlink(), 'RECEIPT_DIRECTORY_SYMLINK')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / ('b1c-consolidated-' + uuid.uuid4().hex + '.json')
    with path.open('x', encoding='utf-8') as f:
        json.dump(report, f, indent=2, sort_keys=True)
        f.write('\n')
    return str(path)


def run(args) -> int:
    report = {
        'schema': 'skybind-b1c-consolidated-device-v1',
        'state': 'BLOCKED', 'reason': None,
        'pipeline_id': args.pipeline_id, 'mode': args.mode,
        'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
        'source_gate_sha256': b1c.digest(Path(__file__)),
        'device_qualified': False, 'release_qualified': False,
        'production_broker_enabled': False, 'go_package_attestor_implemented': False,
        'external_cross_uid_acceptance': False, 'automatic_uninstall': False,
        'automatic_data_clear': False, 'automatic_reboot': False,
        'installation_performed': False, 'tests': {},
    }
    try:
        sha = current_source_sha()
        report['source_sha'] = sha
        attestation = verified_new_attestation(args.pipeline_id, sha)
        report['github_run_id'] = attestation['run_id']
        report['artifact_zip_sha256'] = attestation['artifact_zip_sha256']
        archive = b1c.verified_archive(attestation)
        with tempfile.TemporaryDirectory(prefix='skybind-b1c-consolidated-') as folder:
            tmp = Path(folder)
            pair = b1c.copy_verified_pair(archive, attestation, tmp)
            adb = shutil.which('adb')
            b1c.need(adb is not None, 'ADB_NOT_FOUND')
            serial = b1c.chosen_device(adb, args.serial)
            report['device_serial_sha256'] = hashlib.sha256(serial.encode()).hexdigest()
            report['device_api'] = int(b1c.getprop(adb, serial, 'ro.build.version.sdk'))
            b1c.need(report['device_api'] >= 28, 'DEVICE_API_BELOW_BINDER_TEST_MINIMUM')
            state = b1c.check_installed(adb, serial, tmp, attestation)
            report['installed_pair'] = state
            if state == 'MATCHED':
                first = identity_survey.package_uid_map(identity_survey.adb_check(adb, serial, 'pm', 'list', 'packages', '-U', '--user', '0'))
                second = identity_survey.package_uid_map(identity_survey.adb_check(adb, serial, 'cmd', 'package', 'list', 'packages', '-U', '--user', '0'))
                identity_survey.validate_uid_mapping(first, second)
                b1c.need(identity_survey.adb_check(adb, serial, 'getenforce').strip() == 'Enforcing',
                         'SELINUX_NOT_ENFORCING')
                report['uid_ownership'] = 'PASS'
                report['selinux'] = 'Enforcing'
            if state == 'ABSENT' and args.install_missing and args.mode == 'instrument':
                b1c.install_missing(adb, serial, pair)
                report['installation_performed'] = True
                state = b1c.check_installed(adb, serial, tmp, attestation)
                report['installed_pair'] = state
                if state == 'MATCHED':
                    first = identity_survey.package_uid_map(identity_survey.adb_check(adb, serial, 'pm', 'list', 'packages', '-U', '--user', '0'))
                    second = identity_survey.package_uid_map(identity_survey.adb_check(adb, serial, 'cmd', 'package', 'list', 'packages', '-U', '--user', '0'))
                    identity_survey.validate_uid_mapping(first, second)
                    b1c.need(identity_survey.adb_check(adb, serial, 'getenforce').strip() == 'Enforcing', 'SELINUX_NOT_ENFORCING')
                    report['uid_ownership'] = 'PASS'
                    report['selinux'] = 'Enforcing'
            if state == 'ABSENT':
                report['state'] = 'PREPARED_INSTALL_REQUIRED'
            elif args.mode == 'preflight':
                report['state'] = 'PASS_B1C_CONSOLIDATED_PAIR_PROVENANCE'
            else:
                methods = ','.join(f'{cl}#{fn}' for cl, fn in sorted(CASES))
                code, out, _ = b1c.adb_call(adb, serial, 'shell', 'am', 'instrument', '-w', '-r',
                                           '-e', 'class', methods, b1c.RUNNER, timeout=200)
                b1c.need(code == 0, 'INSTRUMENTATION_SHELL_COMMAND_FAILED')
                report['tests'] = parse_four_cases(out)
                report['state'] = 'PASS_B1C_CONSOLIDATED_IN_APP_BINDER_TESTS_NOT_CROSS_UID'
    except (b1c.Blocked, ValueError, KeyError, OSError, subprocess.SubprocessError,
            json.JSONDecodeError) as exc:
        report['reason'] = exc.reason if isinstance(exc, b1c.Blocked) else type(exc).__name__.upper()
    report['receipt'] = write_once(report)
    print(json.dumps({k: report.get(k) for k in ('state', 'reason','receipt','installed_pair','tests')}, sort_keys=True))
    return 0 if report['state'].startswith('PASS_') else 2


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pipeline-id', required=True, help='NEW native Devtool Actions-06 pipeline after source commit')
    p.add_argument('--mode', choices=('preflight','instrument'), default='preflight')
    p.add_argument('--serial')
    p.add_argument('--install-missing', action='store_true')
    args = p.parse_args()
    if args.install_missing and args.mode != 'instrument':
        p.error('--install-missing requires --mode instrument')
    return run(args)


if __name__ == '__main__':
    raise SystemExit(main())
