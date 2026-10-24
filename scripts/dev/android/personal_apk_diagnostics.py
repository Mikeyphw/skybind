#!/usr/bin/env python3
"""Bounded, public compiled-APK identity diagnostics for failed hosted verification.

Does not inspect or emit keystores, private data, APK contents, environment
secrets or unfiltered manifest text. Never emits acceptance or qualification.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from personal_apk import (APP_FILE, TEST_FILE, aapt_bin, CandidateError,
                          BADGING_PACKAGE_LINE, BADGING_ATTRIBUTE,
                          ALLOWED_PERMISSIONS, PERMISSION, parse_compiled_manifest_tree)

FIELDS = ('package', 'android:versionCode', 'android:versionName',
          'android:minSdkVersion', 'android:targetSdkVersion',
          'android:targetPackage', 'android:name')
ELEM = re.compile(r'^\s*E: (manifest|uses-sdk|instrumentation)\b', re.M)
ATTR = re.compile(r'^\s*A: (package|android:versionCode|android:versionName|'
                  r'android:minSdkVersion|android:targetSdkVersion|android:targetPackage)'
                  r'(?=\(|=)', re.M)
BADGE = re.compile(r'^(package:|sdkVersion:|targetSdkVersion:|instrumentation:)', re.M)

def examine(path: Path, tool: str) -> dict:
    result = {'apk': path.name}
    if path.name not in (APP_FILE, TEST_FILE) or not path.is_file() or path.is_symlink():
        result['status'] = 'NO_EXPECTED_APK'
        return result
    for label, argv in (('badging', [tool, 'dump', 'badging', str(path)]),
                        ('xmltree', [tool, 'dump', 'xmltree', str(path), 'AndroidManifest.xml'])):
        try:
            proc = subprocess.run(argv, text=True, capture_output=True, timeout=20)
            output = proc.stdout[:150000]
            package_lines = BADGING_PACKAGE_LINE.findall(output) if label == 'badging' else []
            attrs = BADGING_ATTRIBUTE.findall(package_lines[0]) if len(package_lines) == 1 else []
            result[label] = {
                'exit': proc.returncode, 'stdout_length': len(proc.stdout),
                'package_line_count': len(package_lines) if label == 'badging' else None,
                'package_attribute_state': ({key: (
                    'duplicate' if sum(a == key for a, _ in attrs) > 1 else
                    'empty' if any(a == key and v == '' for a, v in attrs) else
                    'present' if any(a == key for a, _ in attrs) else 'absent')
                    for key in ('name', 'versionCode', 'versionName')}
                    if label == 'badging' else None),
                'stderr_length': len(proc.stderr),
                # Emit only whitelisted attribute/element names and presence,
                # never values that might originate from arbitrary APK text.
                'fields': sorted(set(ATTR.findall(output))) if label == 'xmltree' else [],
                'elements': sorted(set(ELEM.findall(output))) if label == 'xmltree' else [],
                'badging_headers': sorted(set(BADGE.findall(output))) if label == 'badging' else [],
                'lines': len(output.splitlines()),
            }
        except (OSError, subprocess.TimeoutExpired):
            result[label] = {'error': 'AAPT_INVOCATION_FAILED'}
    safe = lambda values: sorted(v for v in values
                    if re.fullmatch(r'[a-zA-Z0-9_.]{1,160}', v))[:32]
    # Permission names are public APK capabilities, not signer material. Only
    # bounded, syntactically safe names are emitted; the raw XML is never logged.
    try:
        proc = subprocess.run([tool, 'dump', 'permissions', str(path)],
                              text=True, capture_output=True, timeout=20)
        if proc.returncode == 0 and len(proc.stdout) <= 150000:
            listed = set(PERMISSION.findall(proc.stdout))
            result['permissions_report'] = {
                'exit': proc.returncode, 'count': len(listed),
                'missing_expected': safe(ALLOWED_PERMISSIONS - listed),
                'unexpected': safe(listed - ALLOWED_PERMISSIONS),
                'entries': safe(listed),
            }
    except (OSError, subprocess.TimeoutExpired):
        result['permissions_report'] = {'status': 'AAPT_PERMISSIONS_UNAVAILABLE'}
    try:
        raw = subprocess.run([tool, 'dump', 'xmltree', str(path), 'AndroidManifest.xml'],
                             text=True, capture_output=True, timeout=20)
        if raw.returncode == 0 and 0 < len(raw.stdout) <= 150000:
            info = parse_compiled_manifest_tree(raw.stdout,
                                                android_test=path.name == TEST_FILE)
            names = set(info['permissions'])
            result['compiled_permissions'] = {
                'count': len(names),
                'missing_expected': safe(ALLOWED_PERMISSIONS - names),
                'unexpected': safe(names - ALLOWED_PERMISSIONS),
                'entries': safe(names),
                'receiver_permission_signature_protected':
                    info['receiver_permission_signature_protected'],
            }
        else:
            result['compiled_permissions'] = {'status': 'XML_PERMISSION_PARSE_UNAVAILABLE'}
    except (OSError, subprocess.TimeoutExpired, CandidateError, ValueError):
        result['compiled_permissions'] = {'status': 'XML_PERMISSION_PARSE_UNAVAILABLE'}
    return result

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--app', type=Path, required=True)
    ap.add_argument('--test-apk', type=Path, required=True)
    args = ap.parse_args()
    try:
        tool = aapt_bin() # same executable as the fail-closed verifier
    except CandidateError:
        print(json.dumps({'status': 'DIAGNOSTIC_AAPT_MISSING_NOT_QUALIFIED'}))
        return 0
    for path in (args.app, args.test_apk):
        print(json.dumps(examine(path, tool), sort_keys=True))
    print('DIAGNOSTIC_ONLY_NOT_RELEASE_QUALIFIED')
    return 0

if __name__ == '__main__':
    sys.exit(main())
