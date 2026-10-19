#!/usr/bin/env python3
"""Fail-closed source guard for AndroidX Compose/Espresso API-36 compatibility.

This is NOT an Android build or a device test. The hosted APK workflow must
resolve the declared dependency and the device must rerun the UI tests.
"""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[3]
MODULE = Path('android-app/app/build.gradle.kts')
ESPRESSO = re.compile(
    r'^\s*androidTestImplementation\(\s*"androidx\.test\.espresso:espresso-core:([^"\s]+)"\s*\)\s*$',
    re.MULTILINE,
)
COMPOSE = 'androidTestImplementation("androidx.compose.ui:ui-test-junit4")'
EXPECTED_VERSION = '3.7.0'

class Violation(Exception):
    pass


def check_gradle(code: str) -> None:
    # Ignore full-line comments to avoid false proof from a commented dependency.
    live = '\n'.join(line for line in code.splitlines() if not line.lstrip().startswith('//'))
    versions = ESPRESSO.findall(live)
    if versions != [EXPECTED_VERSION]:
        raise Violation('ESPRESSO_3_7_0_EXPLICIT_ANDROIDTEST_DEPENDENCY_REQUIRED')
    if live.count(COMPOSE) != 1:
        raise Violation('COMPOSE_UI_TEST_DEPENDENCY_MISSING_OR_DUPLICATED')
    if 'androidTestImplementation("androidx.test.espresso:espresso-core:3.5.0")' in live:
        raise Violation('LEGACY_ESPRESSO_DEPENDENCY_FORBIDDEN')


def verify(root: Path = ROOT) -> dict:
    path = root / MODULE
    if not path.is_file() or path.is_symlink():
        raise Violation('ANDROID_MODULE_GRADLE_UNAVAILABLE')
    check_gradle(path.read_text(encoding='utf-8'))
    return {
        'state': 'PASS_M2_ESPRESSO_ANDROID36_SOURCE_COMPAT',
        'explicit_espresso_core': EXPECTED_VERSION,
        'compose_ui_test_present': True,
        'android_apk_compiled': False,
        'device_tests_executed': False,
        'release_qualified': False,
    }


if __name__ == '__main__':
    try:
        print(json.dumps(verify(), sort_keys=True))
    except (Violation, OSError, UnicodeError) as exc:
        print(json.dumps({'state': 'FAILED_OR_BLOCKED', 'reason': str(exc)}, sort_keys=True))
        raise SystemExit(2)
