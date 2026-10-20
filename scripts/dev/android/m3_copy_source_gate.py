#!/usr/bin/env python3
"""Fail-closed consolidated M3 copy/reconcile/consumer source security gate."""
from pathlib import Path
import json
import tomllib

ROOT=Path(__file__).resolve().parents[3]


def verify(root=ROOT):
    def read(p):
        f=root/p
        assert f.is_file() and not f.is_symlink(), 'SOURCE_MISSING:'+p
        return f.read_text()
    kotlin=read('android-app/app/src/androidTest/java/io/github/mikeyphw/skybind/LiveM3CopyAcceptanceTest.kt')
    fixture=read('scripts/dev/android/m3_copy_fixture.py')
    runner=read('scripts/dev/android/m2_live_device.py')
    launcher=read('scripts/devtool/ci_artifacts_device.py')
    ui=read('android-app/app/src/main/java/io/github/mikeyphw/skybind/ui/SkybindApp.kt')
    for word in ('skybind.m3.copy.live','M3DisposableCopy','current.startPreparedJob(preview)',
                 'a.startPreparedJob(preview)','b.cancelOwnedRun(id)','b.startPreparedJob(preview)',
                 'SKYBIND_M3_COPY_FAILED_DUPLICATE_ACCEPTED',
                 'SKYBIND_M3_COPY_FAILED_CROSS_SESSION_CANCEL_ACCEPTED',
                 'SKYBIND_M3_COPY_FAILED_STALE_PROOF_ACCEPTED',
                 'SKYBIND_M3_COPY_FAILED_EVENT_REPLAY','JobState.COMPLETED'):
        # test uses a.startPreparedJob for first call and replays one-shot proof.
        if word=='current.startPreparedJob(preview)': continue
        assert word in kotlin, 'ANDROID_COPY_CASE_MISSING:'+word
    for danger in ('"sync"','jobs.apply','su -c','Runtime.getRuntime','ProcessBuilder','deletefile'):
        assert danger not in kotlin,'ANDROID_COPY_CASE_UNREVIEWED:'+danger
    for required in ("NAME = 'M3DisposableCopy'", "'kind':'copy'", "kind='copy'", "'interval_seconds': 0", "interval_seconds=0",'def fixture_state(phase)',
                     "fixture_state('prepared')", "fixture_state('complete')",'hashlib.sha256',
                     'COPY_DEST_HASH_MISMATCH','COPY_SENTINEL_CHANGED','COPY_FOREIGN_ROOT_ENTRY'):
        if required in ("'kind':'copy'", "'interval_seconds': 0"): continue
        assert required in fixture, 'COPY_FIXTURE_CONTRACT_MISSING:'+required
    # Empty legacy registries are accepted only when jobs:null is explicit,
    # preventing a missing/malformed key from being treated as proof of emptiness.
    for token in ("jobs=reg.get('jobs')", "if jobs is None:",
                  "require('jobs' in reg, 'COPY_REGISTRY_JOBS_MISSING')",
                  "require(isinstance(jobs,list), 'COPY_REGISTRY_INVALID')"):
        assert token in fixture, 'COPY_LEGACY_EMPTY_CONTRACT_MISSING:'+token
    assert 'shutil.rmtree' not in fixture and 'os.system(' not in fixture and 'shell=True' not in fixture
    assert 'job-copy-consent' in ui and 'confirmedCopy' in ui and 'job-confirm-start' in ui
    for required in ('parse_m3_copy','M3_COPY_CASE',"opts.mode == 'm3-copy-live'", 
                     "doc['copy_preflight']", "doc['copy_integrity']", 
                     "doc['m3_copy_device_qualified']=True"):
        assert required in runner,'COPY_RUNNER_MISSING:'+required
    for required in ("'m3-copy-live'",'M3_COPY_WRITES_EXPLICIT_AUTHORIZATION_REQUIRED',
                     'COPY_INTEGRITY_RECEIPT_INVALID','--allow-disposable-copy-writes',
                     "doc['m3_copy_device_qualified']",'release_qualified=False'):
        assert required in launcher, 'COPY_LAUNCHER_MISSING:'+required
    conf=tomllib.loads(read('.devtool.toml'))
    steps=conf['targets']['skybind_release']['workflows']['m3-consolidated-source']
    ids=[v['id'] for v in steps]
    assert ids==['copy-contract','consumer-r0','negatives','regression','hosted-only']
    for i,v in enumerate(steps):
        assert v['depends_on']==ids[:i]
    assert conf['wrapper']['commands']['m3-consolidated-source']['target']=='skybind_release'
    from m3_consumer_contract_gate import verify as consumer_check
    report=consumer_check()
    assert report['external_rclone_compatible'] is False
    assert report['source_build_required_for_consumer_update'] is False
    abi=json.loads(read('docs/contracts/rclone-compat/SKYBIND_CONSUMER_ABI_V1.json'))
    assert abi['abi_major']==1 and abi['available_external_capabilities']==[]
    assert abi['external_transport_status']=='NOT_IMPLEMENTED'
    conformance=json.loads(read('docs/contracts/rclone-compat/M3_CONSUMER_CONFORMANCE.json'))
    assert conformance['integration_lifecycle']['core_rebuild_on_consumer_update'] is False
    assert conformance['chrootctl']['source_hash_policy']=='REFERENCE_ONLY_NOT_RUNTIME_PIN'
    assert conformance['bkx']['source_hash_policy']=='REFERENCE_ONLY_NOT_RUNTIME_PIN'
    return {'status':'PASS_M3_COPY_CONSOLIDATED_SOURCE_ONLY','device_qualified':False,
            'copy_device_qualified':False,'r1_r5_external_clients_qualified':False,
            'release_qualified':False}

if __name__=='__main__':
    try: print(json.dumps(verify(),sort_keys=True))
    except (AssertionError,ValueError,KeyError,OSError,ImportError) as e:
        print(json.dumps({'status':'FAILED','reason':str(e)[:120]}));raise SystemExit(2)
