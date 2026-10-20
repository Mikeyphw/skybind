"""Consolidated M2-L3 source and evidence protocol fixture regressions (no ADB)."""
from pathlib import Path
from unittest.mock import patch
from subprocess import CompletedProcess
from argparse import Namespace
import importlib.util
import io
import contextlib
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


gate = load('m2l3_lifecycle_source', 'scripts/dev/android/m2_lifecycle_source_gate.py')
worker = load('m2l3_lifecycle_runner', 'scripts/dev/android/m2_live_device.py')
process = load('m2l3_lifecycle_process', 'scripts/dev/android/m2_process_live.py')
ci = load('m2l3_lifecycle_ci', 'scripts/devtool/ci_artifacts_device.py')
SUCCESS = '''INSTRUMENTATION_STATUS: class=io.github.mikeyphw.skybind.LiveTransportAcceptanceTest
INSTRUMENTATION_STATUS: numtests=1
INSTRUMENTATION_STATUS: test=liveTransportLossAndFreshReconnect
INSTRUMENTATION_STATUS_CODE: 1
INSTRUMENTATION_STATUS: test=liveTransportLossAndFreshReconnect
INSTRUMENTATION_STATUS_CODE: 0
INSTRUMENTATION_RESULT: stream=OK (1 test)
INSTRUMENTATION_CODE: -1
'''
XML = '''<?xml version="1.0" encoding="UTF-8"?><hierarchy>
  <node package="io.github.mikeyphw.skybind" text="Not authorized"/>
  <node package="io.github.mikeyphw.skybind" text="Connect · root approval required"/>
</hierarchy>'''


class Consolidated(unittest.TestCase):
    def test_source_gate(self):
        self.assertEqual(gate.verify(ROOT)['state'],
                         'PASS_M2_L3_CONSOLIDATED_LIFECYCLE_SOURCE_ONLY')

    def test_transport_exact_success_only(self):
        self.assertEqual(worker.parse_transport_live(SUCCESS),
                         ('PASS_M2_L3_APP_OWNED_TRANSPORT_RECOVERY', None))
        invalids = (SUCCESS.replace('numtests=1', 'numtests=2'),
                    SUCCESS.replace('INSTRUMENTATION_CODE: -1', ''),
                    SUCCESS.replace('INSTRUMENTATION_STATUS_CODE: 0', 'INSTRUMENTATION_STATUS_CODE: -2'),
                    SUCCESS.replace('liveTransportLossAndFreshReconnect', 'wrongMethod'),
                    SUCCESS + 'INSTRUMENTATION_STATUS_CODE: 0\n',
                    SUCCESS + 'FAILURES!!!\n')
        for result in invalids:
            with self.subTest(result=result[-60:]):
                self.assertEqual(worker.parse_transport_live(result)[0], 'FAILED')

    def test_explicit_markers_fail_or_block_even_when_success_reported(self):
        for marker in worker.TRANSPORT_BLOCKED:
            self.assertEqual(worker.parse_transport_live(SUCCESS + marker), ('BLOCKED', marker))
        for marker in worker.TRANSPORT_FAILED:
            self.assertEqual(worker.parse_transport_live(SUCCESS + marker), ('FAILED', marker))
        self.assertEqual(worker.parse_transport_live(SUCCESS +
                         'INSTRUMENTATION_STATUS_CODE: -3\n')[0], 'BLOCKED')

    def test_unselected_and_unauthorized_process_disallowed(self):
        self.assertEqual(ci.select_lanes([]), [])
        self.assertEqual(ci.select_lanes(['m2-process-live,m2-transport-live']),
                         ['m2-process-live', 'm2-transport-live'])
        with self.assertRaisesRegex(process.live.Blocked, 'EXPLICIT_APP_FORCE_STOP_REQUIRED'):
            process.verify_app_cold_launch('emulator-5554', approved=False)
        args = Namespace(test=['m2-process-live'], run_id=4, expected_sha=None,
                         serial=None, remote=None, install=False, skip_install=True,
                         artifact_dir=None, output_root=Path('/tmp'), allow_app_force_stop=False)
        with self.assertRaisesRegex(ci.QualificationError,
                                    'M2_PROCESS_EXPLICIT_FORCE_STOP_AUTHORIZATION_REQUIRED'):
            ci.run(args)
        args.test = ['m2-transport-live']
        args.allow_app_force_stop = True
        with self.assertRaisesRegex(ci.QualificationError,
                                    'APP_FORCE_STOP_FLAG_REQUIRES_PROCESS_LANE'):
            ci.run(args)

    def test_app_process_stop_is_specific_and_temp_dump_cleaned(self):
        seen = []
        pids = iter(['1234\n', '\n', '4321\n'])
        def adb(serial, *cmd, **kwargs):
            seen.append(cmd)
            if cmd[:2] == ('shell', 'pidof'):
                value = next(pids)
                return CompletedProcess([], 0 if value.strip() else 1, value, '')
            if cmd[:3] == ('shell', 'am', 'start'):
                return CompletedProcess([], 0, 'Status: ok\n', '')
            if cmd[:3] == ('shell', 'uiautomator', 'dump'):
                return CompletedProcess([], 0, 'UI hierchary dumped\n', '')
            if cmd[:2] == ('shell', 'cat'):
                return CompletedProcess([], 0, XML, '')
            return CompletedProcess([], 0, '', '')
        with patch.object(process.live, 'adb', side_effect=adb):
            value = process.verify_app_cold_launch('emulator-5554', approved=True)
        self.assertTrue(value['cold_ui_observed'])
        self.assertEqual([x for x in seen if x[:3] == ('shell', 'am', 'force-stop')],
                         [('shell', 'am', 'force-stop', 'io.github.mikeyphw.skybind')])
        self.assertTrue(any(x[:3] == ('shell', 'rm', '-f') for x in seen))
        self.assertFalse(any('su' in x or 'reboot' in x or 'clear' in x for x in seen))

    def test_cold_launch_wrong_ui_is_blocked_even_after_force_stop(self):
        pids = iter(['1234\n', '', '4321\n'])
        seen = []
        def adb(serial, *cmd, **kw):
            seen.append(cmd)
            if cmd[:2] == ('shell', 'pidof'):
                value = next(pids)
                return CompletedProcess([], 0 if value.strip() else 1, value, '')
            if cmd[:2] == ('shell', 'cat'):
                return CompletedProcess([], 0,
                    '<hierarchy><node text="Connected" package="io.github.mikeyphw.skybind"/></hierarchy>', '')
            return CompletedProcess([], 0, 'Status: ok', '')
        with patch.object(process.live, 'adb', side_effect=adb):
            with self.assertRaisesRegex(process.live.Blocked, 'M2_PROCESS_COLD_UI_NOT_OBSERVABLE'):
                process.verify_app_cold_launch('device', approved=True)
        self.assertTrue(any(x[:3] == ('shell', 'rm', '-f') for x in seen))

    def test_end_to_end_process_lane_receipt_is_self_consistent(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            original_store = ci.process.live.store
            def write(receipt, *, dest=None):
                return original_store(receipt, dest=Path(tmp))
            with patch.object(ci.process, 'verify_app_cold_launch', return_value={
                'cold_ui_observed': True, 'new_process_observed': True}), \
                 patch.object(ci.process.live, 'store', side_effect=write):
                result = ci.execute_lane('m2-process-live', 11, 'serial', Path(tmp), None,
                                         'f'*40, 12, allow_app_force_stop=True)
            self.assertEqual(result['state'], 'PASS_M2_L3_APP_PROCESS_COLD_LAUNCH')
            self.assertTrue(Path(result['receipt']).is_file())

    def test_process_lane_receipt_is_narrow_and_must_match_source(self):
        common = dict(schema='skybind-m2-live-v1', source_sha='f'*40, github_run_id=3,
            artifact_id=4, installed_pair_verified=True, signing_verified=True,
            release_qualified=False, device_qualified=False,
            m2_l1_device_qualified=False, m2_l2_device_qualified=False,
            m2_l3_negative_device_qualified=False, m2_l3_transport_device_qualified=False,
            m2_l3_process_device_qualified=True,
            state='PASS_M2_L3_APP_PROCESS_COLD_LAUNCH',
            qualified_scope='M2-L3_APP_FORCE_STOP_COLD_LAUNCH_UI_ONLY')
        self.assertEqual(ci.validated_lane_receipt(common, lane='m2-process-live',
                         run_id=3, sha='f'*40, artifact_id=4)['state'], common['state'])
        for mutated in ({'source_sha': 'e'*40}, {'m2_l3_transport_device_qualified': True},
                        {'m2_l3_process_device_qualified': False}, {'release_qualified': True},
                        {'qualified_scope': 'M2-L3_READONLY_NEGATIVE_BOUNDARIES_ONLY'}):
            with self.subTest(mutated=mutated), self.assertRaises(ci.QualificationError):
                ci.validated_lane_receipt(common|mutated, lane='m2-process-live',
                                          run_id=3, sha='f'*40, artifact_id=4)

    def test_transport_lane_receipt_is_independent(self):
        record = dict(schema='skybind-m2-live-v1', source_sha='f'*40, github_run_id=3,
            artifact_id=4, installed_pair_verified=True, signing_verified=True,
            release_qualified=False, device_qualified=False,
            m2_l1_device_qualified=False, m2_l2_device_qualified=False,
            m2_l3_negative_device_qualified=False, m2_l3_transport_device_qualified=True,
            state='PASS_M2_L3_APP_OWNED_TRANSPORT_RECOVERY',
            qualified_scope='M2-L3_APP_OWNED_TRANSPORT_LOSS_RECOVERY_ONLY')
        self.assertEqual(ci.validated_lane_receipt(record, lane='m2-transport-live',
                         run_id=3, sha='f'*40, artifact_id=4)['state'], record['state'])

    def test_source_gate_negative_regression(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for rel in (gate.TRANSPORT, gate.SESSION, gate.PROCESS,
                        gate.LIVE, gate.CI, gate.CONFIG):
                target=root/rel
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes((ROOT/rel).read_bytes())
            self.assertEqual(gate.verify(root)['state'],
                             'PASS_M2_L3_CONSOLIDATED_LIFECYCLE_SOURCE_ONLY')
            path=root/gate.PROCESS
            path.write_text(path.read_text().replace(
                "raise live.Blocked('EXPLICIT_APP_FORCE_STOP_REQUIRED')", 'pass'))
            with self.assertRaises(gate.Violation):
                gate.verify(root)


if __name__ == '__main__':
    unittest.main()
