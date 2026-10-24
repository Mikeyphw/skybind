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
# aapt may emit an *empty or absent* versionName for generated AndroidTest
# packages. Parse identity fields independently; app release version is still
# compared against the strict expected version in assert_pair().
BADGING_PACKAGE_LINE = re.compile(r'^package: +([^\r\n]+)$', re.M)
BADGING_ATTRIBUTE = re.compile(r"\b([A-Za-z][A-Za-z0-9]*)='([^']*)'")
PERMISSION = re.compile(r"^uses-permission(?:-sdk-23)?: name='([^']+)'", re.M)
MIN_SDK = re.compile(r"^sdkVersion:'([0-9]+)'", re.M)
TARGET_SDK = re.compile(r"^targetSdkVersion:'([0-9]+)'", re.M)

# Compiled AndroidTest APKs may omit the aapt "package:" badging line;
# read the actual binary AndroidManifest.xml rather than inventing package
# identity. aapt XML tree output is produced by the pinned SDK build tools.
XML_ELEMENT = re.compile(r'^([ ]*)E: ([A-Za-z_][A-Za-z0-9_.-]*)\b')
XML_ATTRIBUTE = re.compile(r'^([ ]*)A: ([A-Za-z_][A-Za-z0-9_:-]*)(?:\(0x[0-9a-fA-F]+\))?=(.*)$')
XML_QUOTED = re.compile(r'^"([^"\r\n]*)"(?:\s|$)')
XML_INT = re.compile(r'^\(type 0x10\)0x([0-9a-fA-F]+)(?:\s|$)')

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

def parse_compiled_package_line(badging: str, *, android_test=False):
    """Parse the actual aapt package line, without inventing test metadata.

    AndroidTest may omit versionCode, or aapt may show versionCode='' for
    that absent field. Only the AndroidTest role normalizes empty to None;
    malformed nonempty and duplicated values always fail. The app must have
    a nonempty decimal versionCode. Compiled XML remains authoritative.
    """
    lines = BADGING_PACKAGE_LINE.findall(badging)
    demand(len(lines) == 1, 'COMPILED_PACKAGE_IDENTITY_UNAVAILABLE')
    pairs = BADGING_ATTRIBUTE.findall(lines[0])
    demand(len({key for key, _ in pairs}) == len(pairs),
           'COMPILED_PACKAGE_ATTRIBUTES_AMBIGUOUS')
    fields = dict(pairs)
    package = fields.get('name', '')
    value = fields.get('versionCode')
    # aapt badging can materialize a blank test versionCode even though the
    # binary manifest has no versionCode attribute. A nonempty malformed value
    # is never treated as missing, and the production APK remains strict.
    demand(re.fullmatch(r'[A-Za-z0-9_.]+', package) is not None and
           ((android_test and value in (None, '')) or
            (isinstance(value, str) and re.fullmatch(r'[0-9]+', value) is not None)),
           'COMPILED_PACKAGE_IDENTITY_UNAVAILABLE')
    for key in ('name', 'versionCode', 'versionName'):
        if re.search(r'\b' + key + r'\s*=', lines[0]):
            demand(key in fields, 'COMPILED_PACKAGE_ATTRIBUTE_MALFORMED:' + key)
    code = None if value in (None, '') else int(value)
    demand(code is None or 0 <= code <= 2100000000,
           'COMPILED_PACKAGE_VERSION_CODE_INVALID')
    return package, code, fields.get('versionName', '')


def parse_compiled_manifest_tree(tree: str, *, android_test=False) -> dict:
    """Strictly extract identity from aapt's compiled XML tree, not source XML.

    The root manifest and direct children are tracked by indentation so an
    arbitrary nested attribute cannot impersonate a package or test target.
    Unknown, missing, duplicate, typed-unexpected attributes fail closed.
    """
    demand(0 < len(tree) <= 1_000_000, 'COMPILED_MANIFEST_TREE_INVALID')
    stack = []
    found = {}
    for line in tree.splitlines():
        element = XML_ELEMENT.match(line)
        if element:
            indent, name = len(element.group(1)), element.group(2)
            while stack and stack[-1][0] >= indent:
                stack.pop()
            if not stack:
                demand(name == 'manifest' and not found,
                       'COMPILED_MANIFEST_ROOT_INVALID')
            stack.append((indent, name))
            continue
        attribute = XML_ATTRIBUTE.match(line)
        if not attribute or not stack:
            continue
        indent, name, value = (len(attribute.group(1)), attribute.group(2),
                               attribute.group(3))
        demand(indent > stack[-1][0], 'COMPILED_MANIFEST_ATTRIBUTE_NESTING_INVALID')
        owner = stack[-1][1]
        # Only manifest root and its direct children can define identity.
        if len(stack) == 1 and owner == 'manifest':
            section = 'manifest'
        elif len(stack) == 2 and owner in ('uses-sdk', 'instrumentation',
                                           'application', 'uses-permission', 'uses-permission-sdk-23'):
            section = owner
        else:
            continue
        wanted = {
            'manifest': {'package', 'android:versionCode', 'android:versionName'},
            'uses-sdk': {'android:minSdkVersion', 'android:targetSdkVersion'},
            'instrumentation': {'android:targetPackage'},
            'application': {'android:debuggable'},
            'uses-permission': {'android:name'},
            'uses-permission-sdk-23': {'android:name'},
        }
        if name not in wanted[section]:
            continue
        quoted, numeric = XML_QUOTED.match(value), XML_INT.match(value)
        demand(quoted is not None or numeric is not None,
               'COMPILED_MANIFEST_ATTRIBUTE_TYPE_INVALID:' + name)
        parsed = quoted.group(1) if quoted else int(numeric.group(1), 16)
        key = section + '/' + name
        if section in ('uses-permission', 'uses-permission-sdk-23'):
            found.setdefault('permissions', []).append(parsed)
        else:
            demand(key not in found, 'COMPILED_MANIFEST_ATTRIBUTE_DUPLICATE:' + name)
            found[key] = parsed
    package = found.get('manifest/package')
    code = found.get('manifest/android:versionCode')
    minimum = found.get('uses-sdk/android:minSdkVersion')
    target = found.get('uses-sdk/android:targetSdkVersion')
    demand(isinstance(package, str) and
           re.fullmatch(r'[A-Za-z0-9_.]+', package) is not None,
           'COMPILED_MANIFEST_PACKAGE_IDENTITY_INVALID')
    # The generated AndroidTest manifest can legitimately have no versionCode;
    # its identity is established by package, target, signer and exact bytes.
    # Never interpret a missing app version as valid, or manufacture a code.
    demand((android_test and code is None) or
           (type(code) is int and 0 <= code <= 2100000000),
           'COMPILED_MANIFEST_VERSION_CODE_INVALID')
    demand(type(minimum) is int and type(target) is int and
           1 <= minimum <= target <= 100,
           'COMPILED_MANIFEST_SDK_IDENTITY_INVALID')
    version_name = found.get('manifest/android:versionName', '')
    demand(isinstance(version_name, str), 'COMPILED_MANIFEST_VERSION_NAME_INVALID')
    instrumentation = found.get('instrumentation/android:targetPackage')
    debug = found.get('application/android:debuggable', 0)
    demand(debug in (0, 1, 'true', 'false'), 'COMPILED_MANIFEST_DEBUG_ATTRIBUTE_INVALID')
    return {'package': package, 'version_code': code, 'version_name': version_name,
            'min_sdk': minimum, 'target_sdk': target,
            'instrumentation_for_app': instrumentation == APP,
            'debuggable': debug in (1, 'true'),
            'permissions': sorted(set(found.get('permissions', [])))}


def package_identity(apk: Path):
    demand(apk.is_file() and not apk.is_symlink() and 0 < apk.stat().st_size < 200_000_000,
           'INVALID_APK_FILE')
    tool = aapt_bin()
    badging = run_checked([tool, 'dump', 'badging', str(apk)])
    parsed = None
    badging_id = None
    is_test = apk.name == TEST_FILE
    # Missing package lines are common in generated instrumentation packages.
    # Malformed or ambiguous *present* package lines must never be ignored.
    if BADGING_PACKAGE_LINE.findall(badging):
        package, code, version_name = parse_compiled_package_line(badging, android_test=is_test)
        badging_id = (package, code, version_name)
        minimum, target = MIN_SDK.search(badging), TARGET_SDK.search(badging)
        if minimum is not None and target is not None:
            parsed = {'package': package, 'version_code': code,
                      'version_name': version_name, 'min_sdk': int(minimum.group(1)),
                      'target_sdk': int(target.group(1)),
                      'instrumentation_for_app': "targetPackage='" + APP + "'" in badging,
                      'debuggable': bool(re.search(r'^application-debuggable\s*$', badging, re.M))}
    # The binary manifest is authoritative for instrumentation identity.
    # Always check AndroidTest, including when badging has a package line:
    # generated test badging can add an empty/synthetic version that is absent
    # from the compiled manifest. Missing fields are not invented or accepted
    # as evidence of a source/byte match.
    if is_test or parsed is None:
        tree = run_checked([tool, 'dump', 'xmltree', str(apk), 'AndroidManifest.xml'])
        xml = parse_compiled_manifest_tree(tree, android_test=is_test)
        if badging_id is not None:
            package, code, version_name = badging_id
            demand(package == xml['package'],
                   'BADGING_AND_COMPILED_MANIFEST_IDENTITY_DRIFT')
            # For AndroidTest, aapt can render a synthetic 0 for a binary
            # versionCode that is actually absent. Only that exact case may
            # normalize to null; any other concrete disagreement is a denial.
            demand(code is None or code == xml['version_code'] or
                   (is_test and code == 0 and xml['version_code'] is None),
                   'BADGING_AND_COMPILED_MANIFEST_IDENTITY_DRIFT')
            demand(not version_name or version_name == xml['version_name'],
                   'BADGING_AND_COMPILED_MANIFEST_IDENTITY_DRIFT')
        if parsed is not None:
            demand(all(parsed[field] == xml[field] for field in ('min_sdk', 'target_sdk')),
                   'BADGING_AND_COMPILED_MANIFEST_IDENTITY_DRIFT')
        parsed = xml
    # aapt 'dump permissions' is a *secondary report*, not the authoritative
    # manifest. Some pinned SDK versions emit a partial permission listing.
    # Never interpret such under-reporting as permission removal; instead,
    # inspect the *compiled* XML tree and require precisely the four reviewed
    # permissions. Extra reported privileges remain a hard failure.
    perms = run_checked([tool, 'dump', 'permissions', str(apk)])
    listed = set(PERMISSION.findall(perms))
    if not is_test and listed != ALLOWED_PERMISSIONS:
        demand(not (listed - ALLOWED_PERMISSIONS), 'COMPILED_PERMISSION_DRIFT')
        tree = run_checked([tool, 'dump', 'xmltree', str(apk), 'AndroidManifest.xml'])
        compiled = parse_compiled_manifest_tree(tree, android_test=False)
        # The fallback is allowed only if it describes these EXACT app bytes,
        # not an unrelated nested element or a disagreement with badging.
        for key in ('package', 'version_code', 'version_name', 'min_sdk',
                    'target_sdk', 'debuggable', 'instrumentation_for_app'):
            demand(compiled[key] == parsed[key],
                   'BADGING_AND_COMPILED_MANIFEST_IDENTITY_DRIFT')
        demand(compiled['permissions'] == sorted(ALLOWED_PERMISSIONS),
               'COMPILED_PERMISSION_DRIFT')
        parsed['permissions'] = compiled['permissions']
    else:
        parsed['permissions'] = sorted(listed)
    return parsed

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
    try:
        info = package_identity(path)
    except CandidateError as exc:
        # Report which known APK role failed; never emit APK bytes or key data.
        raise CandidateError(str(exc) + ':' + path.name) from exc
    return {
        'name': path.name, 'size_bytes': path.stat().st_size,
        'sha256': sha256_file(path),
        'certificate_sha256': cert, **info,
    }

def assert_pair(app, test, *, version):
    demand(app['package'] == APP and test['package'] == TEST, 'PACKAGE_NAME_MISMATCH')
    demand(app['certificate_sha256'] == test['certificate_sha256'], 'APK_TEST_SIGNER_DRIFT')
    demand(type(app['version_code']) is int and app['version_code'] == version and
           (test['version_code'] is None or
            (type(test['version_code']) is int and 0 <= test['version_code'] <= 2100000000)),
           'PERSONAL_VERSION_CODE_MISMATCH')
    # AGP may give the generated AndroidTest package its own versionCode/name.
    # Bind the test to this EXACT hosted app with signer, target ID, source and bytes,
    # not an undocumented equality of the two packages' version metadata.
    # AGP-created test APKs can have versionName='' or no versionName field.
    # Keep the *app* version exact; the test APK is instead bound by its signed
    # identity, instrumentation target package, source SHA and immutable bytes.
    demand(app['version_name'] == '0.2.0-personal.' + str(version) and
           isinstance(test['version_name'], str),
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
