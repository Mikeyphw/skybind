#!/usr/bin/env python3
"""Fail-closed M2-L1 source contract: real RootService, explicit opt-in, no mutations."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[3]
KOTLIN = Path('android-app/app/src/androidTest/java/io/github/mikeyphw/skybind/LiveRootBrowserAcceptanceTest.kt')
RUNNER = Path('scripts/dev/android/m2_live_device.py')
GROUPED = Path('scripts/dev/android/r1_b1c_security_source.py')

class Violation(Exception):
    pass


def need(test, reason):
    if not test:
        raise Violation(reason)


def verify(root=ROOT):
    def read(relative):
        p = root / relative
        need(p.is_file() and not p.is_symlink(), 'MISSING_' + p.name)
        return p.read_text()
    test = read(KOTLIN)
    runner = read(RUNNER)
    group = read(GROUPED)
    for token in (
        'class LiveRootBrowserAcceptanceTest',
        'assumeTrue("SKYBIND_LIVE_NOT_REQUESTED"',
        'RootReadSession(app)', 'withContext(Dispatchers.Main) { session.connect() }',
        'session.snapshot()', 'session.browse(remote, "")',
        'session.close()', 'withContext(NonCancellable + Dispatchers.Main) { session.close() }',
        'SKYBIND_LIVE_FAILED_STALE_AFTER_CLOSE',
        'SKYBIND_LIVE_FAILED_RECONNECT_SNAPSHOT',
        'SKYBIND_LIVE_BLOCKED_NO_REMOTE',
    ):
        need(token in test, 'LIVE_TEST_CONTRACT_MISSING_' + token)
    for forbidden in ('Shell.cmd', 'su -c', 'Runtime.getRuntime', 'adb shell',
                      'RootService.stop', 'am force-stop', 'pm clear', 'FileOutputStream'):
        need(forbidden not in test, 'LIVE_TEST_MUTATION_OR_SHELL_' + forbidden)
    for token in (
        "CASE = APP + '.LiveRootBrowserAcceptanceTest#liveReadBrowseAndReconnect'",
        "'-e', 'skybind.live', 'true'",
        "'--mode', choices=('preflight','live','ui-live','negative-live')",
        'github(opts.run_id, sha)', 'verify_candidate(folder, opts.run_id, sha,',
        'installed_pair(device, manifest, read_pin())',
        'parse_live(outcome.stdout)', 'return_code',
        "'release_qualified': False",
    ):
        # Slightly different spelling for source contract markers is okay only
        # where explicitly enumerated below, not for security guard inputs.
        if token == 'return_code':
            need('outcome.returncode == 0' in runner, 'IGNORE_INSTRUMENTATION_EXIT')
        elif token == "'release_qualified': False":
            need('release_qualified=False' in runner, 'RELEASE_OVERCLAIM')
        else:
            need(token in runner, 'DEVICE_RUNNER_CONTRACT_MISSING_' + token)
    for forbidden in ("'uninstall'", "'install'", "'force-stop'", "'clear'", "'reboot'",
                      "'su'", "'sh', '-c'", 'os.system(', 'shell=True'):
        need(forbidden not in runner, 'DEVICE_RUNNER_MUTATION_' + forbidden)
    need("'m2_l1_device_qualified'" in runner and 'github_run_authenticated=False' in runner and
         'device_qualified=False' in runner and 'remote_metadata_verified=False' in runner,
         'PROVENANCE_OR_QUALIFICATION_OVERCLAIM')
    need("'SKYBIND_LIVE_BLOCKED_ROOT_BIND'" in runner and
         "'SKYBIND_LIVE_FAILED_BROWSE'" in runner,
         'FAIL_CLOSED_LIVE_CLASSIFICATION_MISSING')
    need('scripts/dev/android/m2_live_source_gate.py' in group and
         'tests.test_m2_live_device' in group, 'MISSING_GROUPED_REGRESSION_LANE')
    return {'state':'PASS_M2_L1_LIVE_ACCEPTANCE_SOURCE_ONLY',
            'apks_built':False,'device_tested':False,'privileged_mutations':False,
            'release_qualified':False}


if __name__ == '__main__':
    try: print(json.dumps(verify(),sort_keys=True))
    except (Violation,OSError,UnicodeError) as exc:
        print(json.dumps({'state':'FAILED_OR_BLOCKED','reason':str(exc)},sort_keys=True))
        raise SystemExit(2)
