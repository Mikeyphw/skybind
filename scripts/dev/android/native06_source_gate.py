#!/usr/bin/env python3
"""NATIVE-06 safety/source shape gate. Not an Android compile or device receipt."""
from pathlib import Path
import json
ROOT = Path(__file__).resolve().parents[3]

def source(path):
    p = ROOT / path
    if p.is_symlink() or not p.is_file():
        raise RuntimeError('REQUIRED_NATIVE06_SOURCE_MISSING:' + path)
    return p.read_text()

def check():
    runner = source('scripts/dev/android/native06_personal_acceptance.py')
    live = source('android-app/app/src/androidTest/java/io/github/mikeyphw/skybind/NativePersonalLiveTest.kt')
    for code in ('EXACT_COMMITTED_APK_SOURCE_REQUIRED', 'HOSTED_WORKFLOW_SOURCE_MISMATCH',
                 'EXACT_SIGNED_PERSONAL_APP_AND_TEST_NOT_INSTALLED',
                 'INSTALLED_NATIVE_DAEMON_BINARY_MISMATCH_OR_UNREADABLE',
                 'INSTRUMENTATION_FAILED_OR_SKIPPED', 'RECEIPT_NOT_FROM_OPERATOR_STATE_DIRECTORY',
                 'SAME_SOURCE_INSTALLED_MODULE_EVIDENCE_MISSING',
                 'EXPLICIT_ALL_OWNER_APPROVAL_FLAGS_REQUIRED',
                 'APPROVAL_ARTIFACT_DRIFT', 'REQUIRED_DEVICE_LANE_MISSING',
                 'READONLY_MUST_NOT_HAVE_MUTATION_CONSENT',
                 'MOUNT_FIXTURE_PATH_ALREADY_PRESENT_OR_UNKNOWN',
                 'MOUNT_FIXTURE_CLEANUP_FAILED_INSPECT_DEVICE',
                 'ACTIVE_SKYBIND_DAEMON_BINARY_STALE_OR_UNREADABLE',
                 'ANDROID_36_QUALIFICATION_TARGET_REQUIRED'):
        if code not in runner:
            raise RuntimeError('MISSING_NATIVE06_FAIL_CLOSED_GUARD:' + code)
    for code in ('automaticForegroundRootNoManualConnect', 'mountsMatchAuthoritativeDaemon',
                 'disposableMountStartRestartStopReconcile',
                 'NATIVE_PERSONAL_LIFECYCLE_NOT_AUTHORIZED',
                 'global reconcile requires isolated inactive registry',
                 'root.previewMount("start", name)', 'root.previewMount("restart", name)',
                 'root.previewMount("stop", name)', 'root.previewMount("reconcile", "")',
                 'root.previewConfig("delete", name, null)',
                 '"skybind.native.personal.mountpoint"',
                 'mountpoint = mountpoint,'):
        if code not in live:
            raise RuntimeError('MISSING_NATIVE06_DEVICE_CONTRACT:' + code)
    if 'onNodeWithTag("connect-readonly").performClick()' in live:
        raise RuntimeError('AUTO_ROOT_TEST_MUST_NOT_USE_MANUAL_CONNECT')
    if any(x in runner for x in ("adb(serial, 'uninstall'", "adb(serial, 'install'", "'pm', 'clear'")):
        raise RuntimeError('NATIVE06_MUST_NOT_INSTALL_OR_CLEAR_DEVICE')
    return {'status':'PASS_NATIVE06_ACCEPTANCE_SOURCE_ONLY', 'android_built':False,
            'device_qualified':False, 'release_qualified':False}

if __name__ == '__main__':
    print(json.dumps(check(),sort_keys=True))
