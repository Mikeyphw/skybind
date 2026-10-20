#!/usr/bin/env python3
"""M2-L3 negative-lane source-bound contract; never executes Android or GitHub."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[3]
TEST = Path('android-app/app/src/androidTest/java/io/github/mikeyphw/skybind/LiveNegativeAcceptanceTest.kt')
SESSION = Path('android-app/app/src/main/java/io/github/mikeyphw/skybind/bridge/RootReadSession.kt')
RUNNER = Path('scripts/dev/android/m2_live_device.py')
CI = Path('scripts/devtool/ci_artifacts_device.py')
CONFIG = Path('.devtool.toml')

class Violation(Exception):
    pass


def require(value, error):
    if not value:
        raise Violation(error)


def verify(root=ROOT):
    def read(path):
        file = root / path
        require(file.is_file() and not file.is_symlink(), 'MISSING_' + path.name)
        return file.read_text()
    test, session, runner, ci, config = map(read, (TEST, SESSION, RUNNER, CI, CONFIG))
    for token in ('class LiveNegativeAcceptanceTest',
        '"skybind.negative.live"', 'RootReadSession(app)',
        'LinkState.NOT_AUTHORIZED, before.link', 'before.activeJobs.isEmpty()',
        'withContext(Dispatchers.Main) { session.connect() }',
        'session.browse(pair.first, pair.second)', '"../escape"',
        '"invalid:remote"', 'LinkState.ONLINE, stillLive.link',
        'withContext(NonCancellable + Dispatchers.Main) { session.close() }',
        'LinkState.NOT_AUTHORIZED, offline.link', 'offline.timeline.isEmpty()',
        'SKYBIND_NEGATIVE_BLOCKED_ROOT_AUTH', 'SKYBIND_NEGATIVE_FAILED_TEARDOWN_LEAK'):
        require(token in test, 'NEGATIVE_REAL_TEST_REQUIRED:' + token)
    for unsafe in ('Shell.cmd(', 'su -c', 'RootService.stop(', 'am force-stop',
        'pm clear', 'Runtime.getRuntime()', 'deleteFile(', 'FileOutputStream(',
        'grantRoot(', 'revokeRoot(', 'killProcess('):
        require(unsafe not in test and unsafe not in runner, 'NEGATIVE_MUTATION:' + unsafe)
    require('if (connection !== this) return' in session and
        session.index('connection = null\n        remote = null\n        reader.reset()') <
        session.index('old?.let { runCatching { RootService.unbind(it) } }'),
        'SESSION_STALE_BINDER_CALLBACK_GUARD_MISSING')
    for token in ("NEGATIVE_CASE = APP + '.LiveNegativeAcceptanceTest#liveReadOnlyNegativeBoundaries'",
        "'-e', 'skybind.negative.live', 'true'", "'negative-live'", 'parse_negative_live(',
        'PASS_M2_L3_READONLY_NEGATIVE_BOUNDARIES', 'm2_l3_negative_device_qualified=False',
        "doc['m2_l3_negative_device_qualified'] = True"):
        require(token in runner, 'RUNNER_NEGATIVE_SCOPE_MISSING:' + token)
    for token in ("'m2-negative-live': 'negative-live'", 'm2_l3_negative_device_qualified=False',
        "record.get('m2_l3_negative_device_qualified', False) is (lane == 'm2-negative-live')",
        'M2-L3_READONLY_NEGATIVE_BOUNDARIES_ONLY', "'LANE_SCOPE_MISMATCH'",
        'live.verify_candidate(folder, args.run_id, sha, pin)',
        'live.installed_pair(serial, manifest, pin)', "require(args.install, 'EXPLICIT_INSTALL_REQUIRED')"):
        require(token in ci, 'CI_NEGATIVE_SOURCE_GUARD_MISSING:' + token)
    for token in ('[targets.skybind_release.jobs.m2-negative-source]',
        '[targets.skybind_release.jobs.m2-negative-unit]',
        'm2-negative-source = [', '[wrapper.commands.m2-negative-source]'):
        require(token in config, 'DEVTOOL_JOB_MISSING:' + token)
    return {'state':'PASS_M2_L3_READONLY_NEGATIVE_SOURCE_ONLY',
            'real_root_refusal_tested':False,'real_daemon_death_tested':False,
            'real_process_death_tested':False,'device_qualified':False,
            'apks_built':False,'release_qualified':False}


if __name__ == '__main__':
    try:
        print(json.dumps(verify(),sort_keys=True))
    except (Violation,OSError,UnicodeError) as exc:
        print(json.dumps({'state':'FAILED_OR_BLOCKED','reason':str(exc)},sort_keys=True))
        raise SystemExit(2)
