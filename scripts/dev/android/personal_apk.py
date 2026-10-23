#!/usr/bin/env python3
"""GitHub-only personal APK candidate producer; offline byte/signer/package verifier.

No release qualification is issued. No APK is built, installed or signed here.
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

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import apk_manifest

REPO = 'Mikeyphw/skybind'
APP = 'io.github.mikeyphw.skybind'
TEST = APP + '.test'
ARTIFACT = 'skybind-personal-apk-candidate-unqualified'
HEX = re.compile(r'[0-9a-f]{64}\Z')
SHA = re.compile(r'[0-9a-f]{40}\Z')
APP_FILE = 'app-personal.apk'
TEST_FILE = 'app-personal-androidTest.apk'
MANIFEST_FILE = 'PERSONAL_APK_MANIFEST.json'
ALLOWED_PERMISSIONS = frozenset({
    'android.permission.FOREGROUND_SERVICE',
    'android.permission.FOREGROUND_SERVICE_SPECIAL_USE',
    'android.permission.POST_NOTIFICATIONS',
    'android.permission.ACCESS_NETWORK_STATE',
})
BADGING_PACKAGE = re.compile(r"^package: name='([^']+)' versionCode='([0-9]+)' versionName='([^']+)'", re.M)
PERMISSION = re.compile(r"^uses-permission(?:-sdk-23)?: name='([^']+)'", re.M)
MIN_SDK = re.compile(r"^sdkVersion:'([0-9]+)'", re.M)
TARGET_SDK = re.compile(r"^targetSdkVersion:'([0-9]+)'", re.M)

class CandidateError(Exception):
    pass

def demand(condition, code):
    if not condition:
        raise CandidateError(code)

def run_checked(args, *, timeout=60):
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CandidateError('REQUIRED_TOOL_FAILED:' + Path(args[0]).name) from exc
    demand(proc.returncode == 0, 'REQUIRED_TOOL_REJECTED:' + Path(args[0]).name)
    return proc.stdout

def aapt_bin():
    selected = shutil.which('aapt')
    if not selected:
        sdk = os.getenv('ANDROID_HOME') or os.getenv('ANDROID_SDK_ROOT')
        if sdk:
            paths = list(Path(sdk, 'build-tools').glob('*/aapt'))
            if paths:
                selected = str(sorted(paths, reverse=True)[0])
    demand(selected is not None, 'AAPT_REQUIRED_FOR_PACKAGE_AND_PERMISSION_VERIFICATION')
    return selected

def package_identity(apk: Path):
    demand(apk.is_file() and not apk.is_symlink() and 0 < apk.stat().st_size < 200_000_000,
           'INVALID_APK_FILE')
    tool = aapt_bin()
    badging = run_checked([tool, 'dump', 'badging', str(apk)])
    m = BADGING_PACKAGE.search(badging)
    demand(m is not None, 'COMPILED_PACKAGE_IDENTITY_UNAVAILABLE')
    permissions = frozenset(PERMISSION.findall(run_checked([tool, 'dump', 'permissions', str(apk)])))
    minimum, target = MIN_SDK.search(badging), TARGET_SDK.search(badging)
    demand(minimum is not None and target is not None, 'COMPILED_SDK_METADATA_UNAVAILABLE')
    return {
        'package': m.group(1), 'min_sdk': int(minimum.group(1)), 'target_sdk': int(target.group(1)), 'version_code': int(m.group(2)),
        'version_name': m.group(3), 'permissions': sorted(permissions),
        'debuggable': bool(re.search(r'^application-debuggable\s*$', badging, re.M)),
        'instrumentation_for_app': "targetPackage='" + APP + "'" in badging,
    }

def sha256_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as inp:
        for block in iter(lambda: inp.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()

def file_record(path):
    demand(path.name in (APP_FILE, TEST_FILE), 'UNEXPECTED_APK_NAME')
    cert = apk_manifest.apk_cert(path)
    demand(isinstance(cert, str) and HEX.fullmatch(cert) is not None,
           'SIGNED_APK_VERIFICATION_REQUIRED')
    info = package_identity(path)
    return {
        'name': path.name, 'size_bytes': path.stat().st_size,
        'sha256': sha256_file(path),
        'certificate_sha256': cert, **info,
    }

def assert_pair(app, test, *, version):
    demand(app['package'] == APP and test['package'] == TEST, 'PACKAGE_NAME_MISMATCH')
    demand(app['certificate_sha256'] == test['certificate_sha256'], 'APK_TEST_SIGNER_DRIFT')
    demand(app['version_code'] == version and
           isinstance(test['version_code'], int) and test['version_code'] > 0,
           'PERSONAL_VERSION_CODE_MISMATCH')
    # AGP may give the generated AndroidTest package its own versionCode/name.
    # Bind the test to this EXACT hosted app with signer, target ID, source and bytes,
    # not an undocumented equality of the two packages' version metadata.
    demand(app['version_name'] == '0.2.0-personal.' + str(version) and
           isinstance(test['version_name'], str) and bool(test['version_name']),
           'PERSONAL_VERSION_NAME_MISMATCH')
    demand(version >= 2 and version <= 2100000000, 'PERSONAL_VERSION_INVALID')
    demand(app['min_sdk'] == test['min_sdk'] == 26 and
           app['target_sdk'] == test['target_sdk'] == 35, 'COMPILED_SDK_DRIFT')
    demand(app['permissions'] == sorted(ALLOWED_PERMISSIONS), 'COMPILED_PERMISSION_DRIFT')
    demand(not app['debuggable'], 'DEBUGGABLE_PERSONAL_APP_REFUSED')
    demand(test['instrumentation_for_app'], 'ANDROIDTEST_TARGET_ID_MISMATCH')

def source_capability():
    files = [
        'android-app/app/src/main/AndroidManifest.xml',
        'android-app/app/src/main/aidl/io/github/mikeyphw/skybind/bridge/IRootReadBridge.aidl',
        'android-app/app/src/main/java/io/github/mikeyphw/skybind/bridge/RootReadBridgeService.kt',
    ]
    # Prevent silently leaving the rooted Binder capability boundary out of receipts.
    for name in files:
        demand((ROOT / name).is_file(), 'CAPABILITY_SOURCE_ABSENT')
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files}

def github_identity(env):
    demand(env.get('GITHUB_ACTIONS') == 'true' and env.get('GITHUB_REPOSITORY') == REPO and
           env.get('GITHUB_REF') == 'refs/heads/main' and
           env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch', 'HOSTED_DISPATCH_MAIN_REQUIRED')
    sha = env.get('GITHUB_SHA', '')
    run = env.get('GITHUB_RUN_ID', '')
    attempt = env.get('GITHUB_RUN_ATTEMPT', '')
    demand(SHA.fullmatch(sha) is not None and run.isdigit() and int(run) > 0 and
           attempt.isdigit() and int(attempt) > 0, 'GITHUB_IDENTITY_INVALID')
    return {'repository': REPO, 'ref': 'refs/heads/main', 'source_sha': sha,
            'run_id': int(run), 'run_attempt': int(attempt),
            'workflow': 'Skybind Personal APK (candidate only)'}

def make_manifest(app_path, test_path, version, env=None):
    env = os.environ if env is None else env
    identity = github_identity(env)
    pin = env.get('SKYBIND_ANDROID_SIGNER_SHA256', '')
    demand(HEX.fullmatch(pin) is not None, 'EXPECTED_SIGNER_SECRET_MISSING')
    app = file_record(app_path)
    test = file_record(test_path)
    assert_pair(app, test, version=version)
    demand(app['certificate_sha256'] == pin, 'EXISTING_SIGNER_PIN_MISMATCH')
    return {
        'schema_version': 1, 'status': 'PERSONAL_APK_CANDIDATE_ONLY',
        'release_qualified': False, 'device_qualified': False,
        'owner_approved': False, 'independent_attestation': False,
        'channel': 'personal', 'build_type': 'personal', 'signing_key_role': 'existing-persistent-development-key',
        'signing_certificate_pin_sha256': pin, 'artifact_name': ARTIFACT,
        'build_environment': 'GitHub Actions ubuntu-24.04',
        'gradle': '8.11.1', 'agp': '8.9.2', 'kotlin': '2.2.21', 'jdk': '17',
        'compile_sdk': 35, 'target_sdk': 35, 'test_build_type': 'personal',
        'build_invocation': [':app:assemblePersonal', ':app:assemblePersonalAndroidTest'],
        'requested_version_code': version,
        'capability_source_sha256': source_capability(),
        'permission_inventory': sorted(ALLOWED_PERMISSIONS),
        'app': app, 'test_apk': test, **identity,
    }

def verify_manifest(manifest, app_path, test_path, *, expected_sha=None, expected_run=None,
                    expected_pin=None):
    demand(manifest.get('schema_version') == 1 and
           manifest.get('status') == 'PERSONAL_APK_CANDIDATE_ONLY' and
           manifest.get('release_qualified') is False and
           manifest.get('device_qualified') is False and
           manifest.get('owner_approved') is False and
           manifest.get('independent_attestation') is False,
           'MANIFEST_OVERCLAIMS_QUALIFICATION')
    demand(manifest.get('repository') == REPO and manifest.get('ref') == 'refs/heads/main' and
           manifest.get('workflow') == 'Skybind Personal APK (candidate only)' and
           SHA.fullmatch(str(manifest.get('source_sha', ''))) is not None and
           type(manifest.get('run_id')) is int and manifest['run_id'] > 0,
           'MANIFEST_SOURCE_IDENTITY_INVALID')
    demand(not expected_sha or manifest['source_sha'] == expected_sha, 'EXPECTED_SOURCE_MISMATCH')
    demand(not expected_run or manifest['run_id'] == expected_run, 'EXPECTED_RUN_MISMATCH')
    pin = manifest.get('signing_certificate_pin_sha256')
    demand(isinstance(pin, str) and HEX.fullmatch(pin) is not None, 'SIGNER_PIN_INVALID')
    demand(not expected_pin or pin == expected_pin, 'TRUSTED_LOCAL_SIGNER_PIN_MISMATCH')
    demand(manifest.get('channel') == 'personal' and manifest.get('build_type') == 'personal' and
           manifest.get('test_build_type') == 'personal' and
           manifest.get('signing_key_role') == 'existing-persistent-development-key',
           'PERSONAL_CHANNEL_MISMATCH')
    app, test = file_record(app_path), file_record(test_path)
    version = manifest.get('requested_version_code')
    demand(type(version) is int, 'VERSION_TYPE_INVALID')
    assert_pair(app, test, version=version)
    for name, observed in (('app', app), ('test_apk', test)):
        demand(manifest.get(name) == observed, 'ARTIFACT_MANIFEST_MISMATCH:' + name)
    demand(app['certificate_sha256'] == pin, 'APK_SIGNER_PIN_MISMATCH')
    demand(manifest.get('permission_inventory') == sorted(ALLOWED_PERMISSIONS),
           'MANIFEST_PERMISSION_INVENTORY_MISMATCH')
    caps = manifest.get('capability_source_sha256')
    demand(isinstance(caps, dict) and caps and all(isinstance(v, str) and HEX.fullmatch(v)
           for v in caps.values()), 'SOURCE_CAPABILITY_DIGEST_INVALID')
    return {'status': 'PERSONAL_APK_BYTES_AND_SIGNER_VERIFIED_UNQUALIFIED',
            'source_sha': manifest['source_sha'], 'run_id': manifest['run_id'],
            'signer': pin, 'version_code': version, 'app_sha256': app['sha256'],
            'test_apk_sha256': test['sha256'], 'device_qualified': False,
            'release_qualified': False}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='cmd', required=True)
    create = sub.add_parser('create')
    create.add_argument('--app', required=True, type=Path)
    create.add_argument('--test-apk', required=True, type=Path)
    create.add_argument('--output', required=True, type=Path)
    create.add_argument('--version-code', required=True, type=int)
    verify = sub.add_parser('verify')
    verify.add_argument('--app', required=True, type=Path)
    verify.add_argument('--test-apk', required=True, type=Path)
    verify.add_argument('--manifest', required=True, type=Path)
    verify.add_argument('--folder', type=Path, help='Optional containment check for app path')
    verify.add_argument('--expected-sha')
    verify.add_argument('--expected-run-id', type=int)
    verify.add_argument('--expected-signer')
    args = parser.parse_args()
    try:
        if args.cmd == 'create':
            result = make_manifest(args.app, args.test_apk, args.version_code)
            demand(not args.output.exists() and not args.output.is_symlink(), 'MANIFEST_ALREADY_EXISTS')
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + '\n')
            response = {'status': result['status'], 'source_sha': result['source_sha'],
                        'version_code': args.version_code, 'signer': result['signing_certificate_pin_sha256']}
        else:
            demand(args.manifest.is_file() and not args.manifest.is_symlink() and
                   args.manifest.stat().st_size <= 20000, 'MANIFEST_FILE_INVALID')
            if args.folder is not None:
                demand(args.app.resolve().parent == args.folder.resolve(), 'APP_NOT_IN_DECLARED_FOLDER')
            result = json.loads(args.manifest.read_text())
            response = verify_manifest(result, args.app, args.test_apk,
                                       expected_sha=args.expected_sha,
                                       expected_run=args.expected_run_id,
                                       expected_pin=args.expected_signer)
        print(json.dumps(response, sort_keys=True))
    except (CandidateError, ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        reason = str(exc) if isinstance(exc, CandidateError) else type(exc).__name__
        print(json.dumps({'status': 'PERSONAL_APK_BLOCKED', 'reason': reason}, sort_keys=True))
        return 2
    return 0

if __name__ == '__main__':
    sys.exit(main())
