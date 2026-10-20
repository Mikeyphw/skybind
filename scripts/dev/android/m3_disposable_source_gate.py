#!/usr/bin/env python3
"""M3 disposable operations: source-only, negative qualification contract."""
from pathlib import Path
import json
import tomllib

ROOT=Path(__file__).resolve().parents[3]
TEST='android-app/app/src/androidTest/java/io/github/mikeyphw/skybind/LiveM3DisposableAcceptanceTest.kt'

class Violation(Exception): pass

def demand(cond, tag):
    if not cond: raise Violation(tag)

def verify(root=ROOT):
    def get(path):
        p=root/path
        demand(p.is_file() and not p.is_symlink(), 'MISSING_FILE:'+path)
        return p.read_text()
    kotlin=get(TEST)
    runner=get('scripts/dev/android/m2_live_device.py')
    launcher=get('scripts/devtool/ci_artifacts_device.py')
    fixture=get('scripts/dev/android/m3_disposable_fixture.py')
    config=tomllib.loads(get('.devtool.toml'))
    assert_required=[
        'class LiveM3DisposableAcceptanceTest',
        'fun liveDisposableCheckCompletes()', 'fun liveDisposableOwnedCancellation()',
        'skybind.m3.execute.live', 'skybind.m3.cancel.live',
        'M3DisposableCheck', '"check"',
        '/storage/emulated/0/Download/.skybind-m3-disposable/source',
        '/storage/emulated/0/Download/.skybind-m3-disposable/destination',
        'snapshot.definitions.none', 'preview.source != source',
        'preview.destination != destination', 'current.startPreparedJob(preview)',
        'current.cancelOwnedRun(id)', 'current.cancelOwnedRun(foreign)',
        'SKYBIND_M3_DISPOSABLE_BLOCKED_CANCEL_RACE',
        'JobState.CANCELLED', 'JobState.COMPLETED',
        'SKYBIND_M3_DISPOSABLE_FAILED_EVENT_REPLAY',
        'SKYBIND_M3_DISPOSABLE_FAILED_CANCEL_EVENT',
        'withContext(NonCancellable + Dispatchers.Main) { bridge?.close() }'
    ]
    for marker in assert_required:
        demand(marker in kotlin, 'KOTLIN_MISSING:'+marker)
    for token in ('"sync"','"copy"','su -c','Runtime.getRuntime()',
                  'RootService.stop(', 'jobs.apply','mount.start'):
        demand(token not in kotlin, 'KOTLIN_UNREVIEWED:'+token)
    for token in ('M3_EXECUTE_CASE', 'M3_CANCEL_CASE', 'parse_m3_disposable',
                  'M3_DISPOSABLE_BLOCKED', 'M3_DISPOSABLE_FAILED',
                  "getattr(opts, 'allow_disposable_job_execution', False)",
                  "getattr(opts, 'allow_disposable_job_cancellation', False)",
                  "doc['m3_execute_device_qualified'] = True",
                  "doc['m3_cancel_device_qualified'] = True"):
        demand(token in runner, 'RUNNER_MISSING:'+token)
    for token in ("'m3-execute-live': 'm3-execute-live'", "'m3-cancel-live': 'm3-cancel-live'",
        'M3_DISPOSABLE_EXECUTION_EXPLICIT_AUTHORIZATION_REQUIRED',
        'M3_DISPOSABLE_CANCEL_EXPLICIT_AUTHORIZATION_REQUIRED',
        'allow_disposable_job_execution=allow_disposable_job_execution',
        'allow_disposable_job_cancellation=allow_disposable_job_cancellation',
        "record.get('m3_execute_device_qualified', False) is (lane == 'm3-execute-live')",
        "record.get('m3_cancel_device_qualified', False) is (lane == 'm3-cancel-live')",
        "'m3_execute_device_qualified', 'm3_cancel_device_qualified'",
        'release_qualified=False', 'live.installed_pair(serial, manifest, pin)'):
        demand(token in launcher, 'LAUNCHER_MISSING:'+token)
    for token in ('manual-only CHECK', 'NAME = \'M3DisposableCheck\'',
                  "'interval_seconds': 0", "'kind': 'check'",
                  "('jobs.status', 'jobs.preview', 'jobs.apply')",
                  'FIXTURE_RUN_ACTIVE', 'SYNC_PRESENT_REGISTRY_REFUSED',
                  'FIXTURE_FOREIGN_FILE_FOUND', 'check_files()',
                  "if not apply:", 'with (folder/f\'sample-'):
        demand(token in fixture, 'FIXTURE_MISSING:'+token)
    demand('os.system(' not in fixture and 'shutil.rmtree(' not in fixture and
           'subprocess.Popen(' not in fixture and 'shell=True' not in fixture,
           'FIXTURE_UNSAFE_SHELL_OR_RECURSIVE_DELETE')
    steps=config['targets']['skybind_release']['workflows']['m3-disposable-source']
    demand([x['id'] for x in steps]==['guard','fixture-tests','regression','hosted-policy'],
           'DAG_NODE_SET_INVALID')
    demand(steps[1]['depends_on']==['guard'] and
           steps[2]['depends_on']==['guard','fixture-tests'] and
           steps[3]['depends_on']==['guard','fixture-tests','regression'],
           'DAG_DEPENDENCY_INVALID')
    demand(config['wrapper']['commands']['m3-disposable-source']['target']=='skybind_release',
           'DAG_WRAPPER_INVALID')
    return {'state':'PASS_M3_DISPOSABLE_SOURCE_ONLY', 'device_qualified':False,
            'm3_execute_device_qualified':False,'m3_cancel_device_qualified':False,
            'release_qualified':False,'github_compiled':False}

if __name__=='__main__':
    try:print(json.dumps(verify(),sort_keys=True))
    except (Violation,KeyError,ValueError,OSError) as e:
        print(json.dumps({'state':'FAILED_OR_BLOCKED','reason':str(e)}))
        raise SystemExit(2)
