"""Source-only negative and orchestration regression; never claims device qualification."""
import argparse
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]/'scripts/dev/android'
sys.path.insert(0,str(SCRIPTS))
import m2_m3_retest_batch as batch


class FakeResult:
    def __init__(self,stdout,returncode=0):
        self.stdout=stdout
        self.returncode=returncode


def passing(mode):
    name=batch.LANES[mode][0].split('#')[-1]
    return ('INSTRUMENTATION_STATUS: numtests=1\n'
            f'INSTRUMENTATION_STATUS: test={name}\n'
            'INSTRUMENTATION_STATUS_CODE: 1\nINSTRUMENTATION_STATUS_CODE: 0\n'
            'INSTRUMENTATION_RESULT: stream=\nOK (1 test)\nINSTRUMENTATION_CODE: -1\n')


def opts(**update):
    data={'run_id':123,'remote':'GDDavys','serial':None,'artifact_dir':None,'output_dir':None,
          'profile':'readonly','allow_disposable_job_execution':False,
          'allow_disposable_job_cancellation':False,'allow_disposable_copy_writes':False,'allow_app_force_stop':False}
    data.update(update)
    return argparse.Namespace(**data)


class BatchTests(unittest.TestCase):
    def test_profiles_and_authorization(self):
        self.assertEqual(batch.plan('readonly',check=False,cancel=False,copy=False,stop=False),batch.READONLY)
        self.assertEqual(batch.plan('full',check=True,cancel=True,copy=True,stop=True),batch.FULL)
        for flags in [(False,False,False),(True,False,True),(True,True,False)]:
            with self.assertRaises(batch.BatchBlocked):
                batch.plan('full',check=flags[0],cancel=flags[1],copy=flags[2],stop=True)
        with self.assertRaises(batch.BatchBlocked):
            batch.plan('readonly',check=True,cancel=False,copy=False,stop=False)

    def test_complete_nine_mode_names_unique(self):
        self.assertEqual(len(batch.FULL),9)
        self.assertEqual(len(set(batch.FULL)),9)
        self.assertEqual(len(set(batch.FLAGS)),9)
        self.assertEqual(batch.FULL[-2], 'm3-copy-live')
        self.assertEqual(batch.FULL[-1], 'm2-process-live')

    def test_all_lanes_require_exact_terminal_success(self):
        for mode in batch.FULL[:-1]:
            with self.subTest(mode=mode):
                state,reason=batch.classify(mode,passing(mode),0)
                self.assertTrue(state.startswith('PASS_'), (mode,state,reason))
                self.assertEqual(batch.classify(mode,passing(mode),1)[0],'FAILED')
                self.assertEqual(batch.classify(mode,passing(mode)+'FAILURES!!!',0)[0],'FAILED')
                self.assertEqual(batch.classify(mode,passing(mode)+'INSTRUMENTATION_STATUS_CODE: -2',0)[0],'FAILED')
                self.assertEqual(batch.classify(mode,passing(mode).replace('OK (1 test)','',1),0)[0],'FAILED')

    def test_skipped_never_passes(self):
        for mode in batch.FULL[:-1]:
            state,_=batch.classify(mode,'INSTRUMENTATION_STATUS_CODE: -3\n',0)
            self.assertFalse(state.startswith('PASS_'),mode)

    def test_readonly_one_preflight_five_live_cases_and_receipt(self):
        with tempfile.TemporaryDirectory() as d, \
             patch.object(batch,'install_readonly_guard',return_value='a-device') as admission, \
             patch.object(batch,'check_fixture',return_value=None) as fixture, \
             patch.object(batch.live,'adb',side_effect=lambda serial,*a,**k: FakeResult(passing(next(
                 mode for mode in batch.READONLY if batch.LANES[mode][0] in a)))) as adb:
            result=batch.run(opts(output_dir=Path(d)))
            self.assertEqual(result,0)
            self.assertEqual(admission.call_count,1)
            fixture.assert_called_once_with('readonly')
            self.assertEqual(adb.call_count,5)
            receipts=list(Path(d).glob('m2m3-*.json'))
            self.assertEqual(len(receipts),1)
            import json
            data=json.loads(receipts[0].read_text())
            self.assertEqual(data['state'],'PASS_M2_M3_FRESH_READONLY_FIVE_LANE_ONLY')
            self.assertEqual(len(data['cases']),5)
            self.assertFalse(data['m2_m3_device_retests_run'])
            self.assertFalse(data['release_qualified'])
            self.assertFalse(data['external_provider_qualified'])

    def test_full_nine_qualified_only_with_fixture_and_terminal(self):
        import m3_copy_fixture
        checked={'expected_content_sha256':'a'*64}
        with tempfile.TemporaryDirectory() as d, \
             patch.object(batch,'install_readonly_guard',return_value='a-device') as admission, \
             patch.object(batch,'check_fixture',return_value=checked), \
             patch.object(m3_copy_fixture,'fixture_state',return_value={**checked,'destination_verified':True}), \
             patch('m2_process_live.verify_app_cold_launch', return_value={'cold_ui_observed':True,'new_process_observed':True}) as process, \
             patch.object(batch.live,'adb',side_effect=lambda serial,*a,**k: FakeResult(passing(next(
                 mode for mode in batch.FULL if batch.LANES[mode][0] in a)))) as adb:
            rc=batch.run(opts(output_dir=Path(d),profile='full',
                              allow_disposable_job_execution=True,
                              allow_disposable_job_cancellation=True,
                              allow_disposable_copy_writes=True,allow_app_force_stop=True))
            self.assertEqual(rc,0)
            self.assertEqual(admission.call_count,1)
            self.assertEqual(adb.call_count,8)
            process.assert_called_once()
            import json
            data=json.loads(next(Path(d).glob('m2m3-*.json')).read_text())
            self.assertEqual(data['state'],'PASS_M2_M3_FRESH_NINE_LANE_AUTOMATED_RETEST_ONLY')
            self.assertTrue(data['m2_m3_device_retests_run'])
            self.assertEqual(len(data['cases']),9)
            self.assertFalse(data['external_provider_qualified'])

    def test_fail_fast_receipt_and_no_qualification(self):
        with tempfile.TemporaryDirectory() as d, \
             patch.object(batch,'install_readonly_guard',return_value='a-device'), \
             patch.object(batch,'check_fixture',return_value=None), \
             patch.object(batch.live,'adb',return_value=FakeResult('FAILURES!!!',0)) as adb:
            self.assertEqual(batch.run(opts(output_dir=Path(d))),2)
            self.assertEqual(adb.call_count,1)
            import json
            data=json.loads(next(Path(d).glob('m2m3-*.json')).read_text())
            self.assertEqual(data['state'],'BLOCKED_M2_M3_BATCH_INCOMPLETE')
            self.assertFalse(data['m2_m3_device_retests_run'])
            self.assertEqual(len(data['cases']),1)

    def test_no_preflight_if_full_lacks_explicit_consent(self):
        with tempfile.TemporaryDirectory() as d,patch.object(batch,'install_readonly_guard') as admit:
            rc=batch.run(opts(output_dir=Path(d),profile='full'))
            self.assertEqual(rc,2)
            admit.assert_not_called()

    def test_installed_identity_mismatch_no_case_runs(self):
        with tempfile.TemporaryDirectory() as d, \
             patch.object(batch,'install_readonly_guard',side_effect=batch.live.Blocked('INSTALLED_MISMATCH')) as admission, \
             patch.object(batch.live,'adb') as adb:
            self.assertEqual(batch.run(opts(output_dir=Path(d))),2)
            self.assertEqual(admission.call_count,1)
            adb.assert_not_called()

    def test_cli_includes_copy_path_and_required_authorization(self):
        path=SCRIPTS/'m2_live_device.py'
        text=path.read_text()
        self.assertIn("'m3-copy-live'), default='preflight'",text)
        self.assertIn("p.add_argument('--allow-disposable-copy-writes'",text)


if __name__=='__main__': unittest.main()
