"""M3 source-bound negative run/cancel evidence and disposable fixture tests."""
import importlib.util
from pathlib import Path
import tempfile
from unittest import TestCase
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]

def load(filename, mod):
    spec=importlib.util.spec_from_file_location(mod, ROOT/filename)
    obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj);return obj

runner=load('scripts/dev/android/m2_live_device.py','m3_disposable_runner')
launcher=load('scripts/devtool/ci_artifacts_device.py','m3_disposable_launcher')
fixture=load('scripts/dev/android/m3_disposable_fixture.py','m3_disposable_fixture')
gate=load('scripts/dev/android/m3_disposable_source_gate.py','m3_disposable_gate')

def successful(case):
    return f'''INSTRUMENTATION_STATUS: class=io.github.mikeyphw.skybind.LiveM3DisposableAcceptanceTest
INSTRUMENTATION_STATUS: numtests=1
INSTRUMENTATION_STATUS: test={case}
INSTRUMENTATION_STATUS_CODE: 1
INSTRUMENTATION_STATUS: test={case}
INSTRUMENTATION_STATUS_CODE: 0
INSTRUMENTATION_RESULT: stream=OK (1 test)
INSTRUMENTATION_CODE: -1
'''

class M3Disposable(TestCase):
    def test_source_gate(self):
        self.assertEqual(gate.verify(ROOT)['state'],'PASS_M3_DISPOSABLE_SOURCE_ONLY')

    def test_exact_instrumentation_for_both_lanes(self):
        cases={'m3-execute-live':('liveDisposableCheckCompletes','PASS_M3_DISPOSABLE_CHECK_COMPLETION'),
               'm3-cancel-live':('liveDisposableOwnedCancellation','PASS_M3_DISPOSABLE_OWNED_CANCEL')}
        for mode,(case,expected) in cases.items():
            raw=successful(case)
            self.assertEqual(runner.parse_m3_disposable(raw,mode=mode),(expected,None))
            for malformed in (raw.replace('numtests=1','numtests=2'), raw.replace('CODE: -1','CODE: 0'),
                              raw.replace(case,'unexpected'),raw+'FAILURES!!!\n',
                              raw+'INSTRUMENTATION_STATUS_CODE: 0\n'):
                self.assertEqual(runner.parse_m3_disposable(malformed,mode=mode)[0],'FAILED')
            for blocked in runner.M3_DISPOSABLE_BLOCKED:
                self.assertEqual(runner.parse_m3_disposable(raw+blocked,mode=mode),('BLOCKED',blocked))
            for failed in runner.M3_DISPOSABLE_FAILED:
                self.assertEqual(runner.parse_m3_disposable(raw+failed,mode=mode),('FAILED',failed))

    def test_no_implicit_lane_or_authorization(self):
        self.assertEqual(launcher.select_lanes([]),[])
        self.assertEqual(launcher.select_lanes(['m3-execute-live','m3-cancel-live']),
                         ['m3-execute-live','m3-cancel-live'])
        for bad in ('job.run','m3-unsafe-live','m3-preview-live --allow-disposable-job-execution'):
            with self.assertRaises(launcher.QualificationError): launcher.select_lanes([bad])

    def test_exact_receipt_scope_and_no_release_promotion(self):
        scopes={'m3-execute-live':('m3_execute_device_qualified', 'PASS_M3_DISPOSABLE_CHECK_COMPLETION',
                                'M3_DISPOSABLE_CHECK_START_TO_TERMINAL_EVENTS_ONLY'),
                'm3-cancel-live':('m3_cancel_device_qualified','PASS_M3_DISPOSABLE_OWNED_CANCEL',
                                'M3_DISPOSABLE_SESSION_OWNED_CANCEL_ONLY')}
        for lane,(flag,state,scope) in scopes.items():
            body={'schema':'skybind-m2-live-v1','source_sha':'a'*40,
                  'github_run_id':7,'artifact_id':11,'installed_pair_verified':True,
                  'signing_verified':True,'release_qualified':False,'device_qualified':False,
                  'm2_l1_device_qualified':False,'m2_l2_device_qualified':False,
                  'm2_l3_negative_device_qualified':False,'m2_l3_transport_device_qualified':False,
                  'm2_l3_process_device_qualified':False,'m3_preview_device_qualified':False,
                  'm3_execute_device_qualified':False,'m3_cancel_device_qualified':False,
                  'state':state,'qualified_scope':scope}
            body[flag]=True
            self.assertEqual(launcher.validated_lane_receipt(body,lane=lane,run_id=7,sha='a'*40,artifact_id=11)['state'],state)
            for change in ({'release_qualified':True},{'device_qualified':True},
                           {flag:False},{'m3_preview_device_qualified':True},
                           {'qualified_scope':'M3_ALL'},{'source_sha':'b'*40},
                           {'m3_cancel_device_qualified':True,'m3_execute_device_qualified':True}):
                with self.assertRaises(launcher.QualificationError):
                    launcher.validated_lane_receipt({**body,**change},lane=lane,run_id=7,sha='a'*40,artifact_id=11)

    def test_fixture_ownership_and_no_scheduler(self):
        job=fixture.definition()
        self.assertEqual(job['kind'],'check')
        self.assertTrue(job['enabled'])
        self.assertEqual(job['interval_seconds'],0)
        self.assertTrue(fixture.owned(job))
        self.assertFalse(fixture.owned({**job,'source':'cloud:personal'}))
        with self.assertRaises(fixture.Blocked):
            fixture.reject_unsafe_registry({'jobs':[{'kind':'sync'}]},[])
        with self.assertRaises(fixture.Blocked):
            fixture.reject_unsafe_registry({'jobs':[job]},[{'name':job['name'],'state':'RUNNING'}])

    def test_fixture_bytes_and_guarded_cleanup(self):
        self.assertEqual(len(fixture.payload(0)),4096)
        self.assertNotEqual(fixture.payload(0),fixture.payload(1))
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'fixture'
            with patch.object(fixture,'ROOT',root), patch.object(fixture,'SRC',root/'source'), \
                 patch.object(fixture,'DST',root/'destination'):
                self.assertEqual(fixture.build_files(64),64)
                self.assertEqual(fixture.check_files(),64)
                (root/'source'/'foreign').write_text('not ours')
                with self.assertRaises(fixture.Blocked): fixture.cleanup_files()
                self.assertTrue((root/'source'/'foreign').is_file())
                (root/'source'/'foreign').unlink()
                fixture.cleanup_files()
                self.assertFalse(root.exists())

    def test_non_authorized_fixture_prepare_is_dry_run(self):
        with patch.object(fixture,'registry',return_value=({'schema_version':1,'revision':0,'jobs':[]},[])), \
             patch.object(fixture,'build_files') as build,patch.object(fixture,'apply_registry') as apply:
            fixture.run('prepare',False,64)
            build.assert_not_called();apply.assert_not_called()
