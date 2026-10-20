"""M2-L3 fail-closed parser, provenance, and source mutation regressions."""
from pathlib import Path
from contextlib import contextmanager
import importlib.util
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

def load(rel,name):
    spec=importlib.util.spec_from_file_location(name,ROOT/rel)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

source=load('scripts/dev/android/m2_negative_source_gate.py','m2l3_negative_source')
worker=load('scripts/dev/android/m2_live_device.py','m2l3_negative_runner')
ci=load('scripts/devtool/ci_artifacts_device.py','m2l3_negative_ci')
SUCCESS="""INSTRUMENTATION_STATUS: class=io.github.mikeyphw.skybind.LiveNegativeAcceptanceTest
INSTRUMENTATION_STATUS: numtests=1
INSTRUMENTATION_STATUS: test=liveReadOnlyNegativeBoundaries
INSTRUMENTATION_STATUS_CODE: 1
INSTRUMENTATION_STATUS: test=liveReadOnlyNegativeBoundaries
INSTRUMENTATION_STATUS_CODE: 0
INSTRUMENTATION_RESULT: stream=OK (1 test)
INSTRUMENTATION_CODE: -1
"""

class NegativeLiveSourceTests(unittest.TestCase):
    def test_source(self):
        self.assertEqual(source.verify(ROOT)['state'],'PASS_M2_L3_READONLY_NEGATIVE_SOURCE_ONLY')

    def test_exact_only_single_negative_success(self):
        self.assertEqual(worker.parse_negative_live(SUCCESS),
                         ('PASS_M2_L3_READONLY_NEGATIVE_BOUNDARIES',None))
        for bad in (SUCCESS.replace('INSTRUMENTATION_CODE: -1',''),
                    SUCCESS.replace('numtests=1','numtests=3'),
                    SUCCESS.replace('liveReadOnlyNegativeBoundaries','otherTest'),
                    SUCCESS.replace('INSTRUMENTATION_STATUS_CODE: 0','INSTRUMENTATION_STATUS_CODE: -1'),
                    SUCCESS + 'INSTRUMENTATION_STATUS_CODE: 0\n',
                    SUCCESS.replace('OK (1 test)','FAILURES!!!')):
            with self.subTest(bad=bad[-55:]):
                self.assertEqual(worker.parse_negative_live(bad)[0], 'FAILED')

    def test_grant_or_environment_block_is_not_pass(self):
        for marker in worker.NEGATIVE_BLOCKED:
            with self.subTest(marker=marker):
                output=SUCCESS+'INSTRUMENTATION_STATUS: stack='+marker+'\n'
                self.assertEqual(worker.parse_negative_live(output),('BLOCKED',marker))
        self.assertEqual(worker.parse_negative_live(SUCCESS+'INSTRUMENTATION_STATUS_CODE: -3\n')[0],
                         'BLOCKED')

    def test_failed_negative_path_never_passes(self):
        for marker in worker.NEGATIVE_FAILED:
            with self.subTest(marker=marker):
                output=SUCCESS+'INSTRUMENTATION_STATUS: stack='+marker+'\n'
                self.assertEqual(worker.parse_negative_live(output),('FAILED',marker))

    def test_only_opted_in_new_lane(self):
        self.assertEqual(ci.select_lanes([]),[])
        self.assertEqual(ci.select_lanes(['m2-negative-live']),['m2-negative-live'])
        self.assertEqual(ci.select_lanes(['m2-process-live']), ['m2-process-live'])
        self.assertEqual(ci.select_lanes(['m2-transport-live']), ['m2-transport-live'])

    def test_narrow_scoped_positive_and_negative_receipts(self):
        receipt=dict(schema='skybind-m2-live-v1',source_sha='a'*40,github_run_id=37,
                     artifact_id=42,installed_pair_verified=True,signing_verified=True,
                     release_qualified=False,device_qualified=False,m2_l1_device_qualified=False,
                     m2_l2_device_qualified=False,m2_l3_negative_device_qualified=True,
                     state='PASS_M2_L3_READONLY_NEGATIVE_BOUNDARIES',
                     qualified_scope='M2-L3_READONLY_NEGATIVE_BOUNDARIES_ONLY')
        self.assertEqual(ci.validated_lane_receipt(receipt,lane='m2-negative-live',
                         run_id=37,sha='a'*40,artifact_id=42)['state'],receipt['state'])
        for change in ({'m2_l1_device_qualified':True},{'m2_l2_device_qualified':True},
                       {'m2_l3_negative_device_qualified':False},{'device_qualified':True},
                       {'release_qualified':True},{'artifact_id':43},
                       {'source_sha':'b'*40},{'qualified_scope':'M2-L2_REAL_COMPOSE_UI_BROWSE_DISCONNECT_RECONNECT'},
                       {'state':'PASS_M2_L2_LIVE_UI_READONLY_RECOVERY'}):
            with self.subTest(change=change),self.assertRaises(ci.QualificationError):
                ci.validated_lane_receipt(receipt|change,lane='m2-negative-live',
                                          run_id=37,sha='a'*40,artifact_id=42)
        with self.assertRaises(ci.QualificationError):
            ci.validated_lane_receipt(receipt,lane='m2-ui-live',
                                      run_id=37,sha='a'*40,artifact_id=42)

    def test_source_gate_detects_removed_negative_case_and_binding_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for rel in (source.TEST,source.SESSION,source.RUNNER,source.CI,source.CONFIG):
                target=root/rel;target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes((ROOT/rel).read_bytes())
            self.assertEqual(source.verify(root)['state'],'PASS_M2_L3_READONLY_NEGATIVE_SOURCE_ONLY')
            session=root/source.SESSION
            good=session.read_text()
            session.write_text(good.replace('if (connection !== this) return','// stale callbacks accepted'))
            with self.assertRaisesRegex(source.Violation,'SESSION_STALE_BINDER_CALLBACK_GUARD_MISSING'):
                source.verify(root)
            session.write_text(good)
            test=root/source.TEST
            test.write_text(test.read_text().replace('"../escape"','"safe/path"'))
            with self.assertRaisesRegex(source.Violation,'NEGATIVE_REAL_TEST_REQUIRED'):
                source.verify(root)

if __name__=='__main__': unittest.main()
