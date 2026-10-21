"""Seven offline negatives for source-bound three-case live device harness."""
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'scripts/dev/android/r1_pm_bridge_device.py'
spec=importlib.util.spec_from_file_location('r1_pm_bridge_device',P)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class PMThreeCaseHarness(unittest.TestCase):
    def args(self,d):
        return types.SimpleNamespace(output_root=d, bkx_signer='a'*64, bkx_uid=10327,
            skybind_uid=10123,skybind_context='u:r:untrusted_app:s0:c123,c456',
            expected_sha='0'*40,apk_run_id=11,go_run_id=22,serial='emulator-5554',restart_skybind=True)
    def test_missing_signer_fails_before_network(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(module.live,'current_source',side_effect=AssertionError('source should not be inspected')):
            a=self.args(Path(d));a.bkx_signer=''
            self.assertEqual(module.perform(a),2)
    def test_same_authority_and_consumer_uid_fails(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(module.live,'current_source',side_effect=AssertionError('not reached')):
            a=self.args(Path(d));a.skybind_uid=a.bkx_uid
            self.assertEqual(module.perform(a),2)
    def test_invalid_selinux_pin_fails(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(module.live,'current_source',side_effect=AssertionError('not reached')):
            a=self.args(Path(d));a.skybind_context='u:r:untrusted_app:s0\nforged'
            self.assertEqual(module.perform(a),2)
    def test_requires_reconnect_between_live_cases(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(module.live,'current_source',side_effect=AssertionError('no remote operations')):
            a=self.args(Path(d));a.restart_skybind=False
            self.assertEqual(module.perform(a),2)
            report=json.loads(next(Path(d).glob('*.json')).read_text())
            self.assertEqual(report['reason'],'SKYBIND_RESTART_REQUIRED_FOR_THREE_INDEPENDENT_CASES')

    def test_agent_negative_instrumentation_complete_and_strict(self):
        tests=sorted(module.AGENT_NEGATIVE_TESTS)
        good='\n'.join('\n'.join('INSTRUMENTATION_STATUS: numtests=4\nINSTRUMENTATION_STATUS: test='+test+\
                       '\nINSTRUMENTATION_STATUS_CODE: '+code for code in ('1','0')) for test in tests)
        good+='\nINSTRUMENTATION_CODE: -1\n'
        receipt=module.interpret_agent_negative_instrumentation(good)
        self.assertEqual(receipt['count'],4)
        for bad in (good.replace('numtests=4','numtests=3',1),
                    good.replace('INSTRUMENTATION_CODE: -1','INSTRUMENTATION_CODE: 0'),
                    good.replace('test='+tests[0],'test=forged',1),
                    good.replace('STATUS_CODE: 0','STATUS_CODE: -2',1),
                    good.replace('INSTRUMENTATION_STATUS_CODE: 0','',1),
                    good+'FAILURES!!!'):
            with self.subTest(bad=bad[-50:]),self.assertRaisesRegex(module.Blocked,'INCOMPLETE'):
                module.interpret_agent_negative_instrumentation(bad)

    def test_three_case_receipts_require_independent_attestation(self):
        with tempfile.TemporaryDirectory() as td:
            args=self.args(Path(td))
            receipts=[
              {'state':'PASS_R1_AUTHENTICATED_PM_CHANNEL_ONLY','reason':None,
               'pm_channel_authenticated':True,'bkx_signer_approved':True},
              {'state':'BLOCKED','reason':'BKX_SIGNER_OR_UID_DENIED',
               'pm_channel_authenticated':True,'bkx_signer_approved':False},
              {'state':'BLOCKED','reason':'AUTHORITY_PEER_NOT_ATTESTED',
               'pm_channel_authenticated':False,'bkx_signer_approved':False}]
            full=[dict(x,schema='skybind-r1-android-to-go-pm-v1',
                      consumer_broker_qualified=False,grants_issued=False,
                      m3_device_retests_run=False) for x in receipts]
            common=(mock.patch.object(module.live,'current_source',return_value=args.expected_sha),
              mock.patch.object(module.live,'github',return_value={'id':44}),
              mock.patch.object(module.ci,'obtain_pair'),
              mock.patch.object(module.live,'verify_candidate',return_value={}),
              mock.patch.object(module.live,'read_pin',return_value={}),
              mock.patch.object(module.live,'choose_device',return_value=args.serial),
              mock.patch.object(module.live,'installed_pair'),
              mock.patch.object(module,'run_agent_negative_instrumentation',return_value={'state':'PASS_R1_PM_AGENT_FOUR_NEGATIVE_TESTS','count':4}),
              mock.patch.object(module,'load_hosted_binary',return_value=Path('/tmp/synthetic')))
            from contextlib import ExitStack
            with ExitStack() as stack:
                for patch in common:stack.enter_context(patch)
                with mock.patch.object(module,'one_case',side_effect=full):
                    self.assertEqual(module.perform(args),0)
                    report=json.loads(next(Path(td).glob('*.json')).read_text())
                    self.assertEqual(report['status'],'PASS_R1_ANDROID_TO_GO_PM_THREE_CASES_PLUS_FOUR_AGENT_NEGATIVES')
                    self.assertEqual(len(report['cases']),3)
                    self.assertEqual(report['android_agent_negative_instrumentation']['count'],4)
                    self.assertFalse(report['external_provider_qualified'])

    def test_instrumentation_shell_failure_is_not_success(self):
        with mock.patch.object(module,'shell',return_value=types.SimpleNamespace(returncode=1,stdout='',stderr='failure')):
            with self.assertRaisesRegex(module.Blocked,'COMMAND_FAILED'):
                module.run_agent_negative_instrumentation('emulator-5554')

    def test_diagnostic_overclaim_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            args=self.args(Path(td))
            with mock.patch.object(module.live,'current_source',return_value=args.expected_sha), \
                 mock.patch.object(module.live,'github',return_value={'id':44}), \
                 mock.patch.object(module.ci,'obtain_pair'), \
                 mock.patch.object(module.live,'verify_candidate',return_value={}), \
                 mock.patch.object(module.live,'read_pin',return_value={}), \
                 mock.patch.object(module.live,'choose_device',return_value=args.serial), \
                 mock.patch.object(module.live,'installed_pair'), \
                 mock.patch.object(module,'run_agent_negative_instrumentation',return_value={'state':'PASS_R1_PM_AGENT_FOUR_NEGATIVE_TESTS','count':4}), \
                 mock.patch.object(module,'load_hosted_binary',return_value=Path('/tmp/synthetic')), \
                 mock.patch.object(module,'one_case',return_value={'schema':'skybind-r1-android-to-go-pm-v1', 'state':'PASS_R1_AUTHENTICATED_PM_CHANNEL_ONLY', 'reason':None,'consumer_broker_qualified':True,'grants_issued':False,'m3_device_retests_run':False}):
                self.assertEqual(module.perform(args),2)
                report=json.loads(next(Path(td).glob('*.json')).read_text())
                self.assertEqual(report['reason'],'DIAGNOSTIC_RECEIPT_OVERCLAIMS_QUALIFICATION')
                self.assertFalse(report['external_provider_qualified'])

    def test_source_identity_mismatch(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(module.live,'current_source',return_value='f'*40):
            a=self.args(Path(d))
            self.assertEqual(module.perform(a),2)
            report=json.loads(next(Path(d).glob('*.json')).read_text())
            self.assertEqual(report['reason'],'SOURCE_IDENTITY_MISMATCH')
            self.assertFalse(report['external_provider_qualified'])
    def test_hosted_go_manifest_wrong_sha(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(module,'shell') as shell:
            shell.return_value=types.SimpleNamespace(stdout=json.dumps({'head_sha':'e'*40,'conclusion':'success',
            'name':'Skybind R1 Android-to-Go PM bridge (unqualified diagnostic)'}))
            with self.assertRaisesRegex(module.Blocked,'GO_DIAGNOSTIC_RUN_MISMATCH'):
                module.load_hosted_binary(7,'f'*40,Path(d))
    def test_missing_hosted_run_success(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(module,'shell') as shell:
            shell.return_value=types.SimpleNamespace(stdout=json.dumps({'head_sha':'f'*40,'conclusion':'failure',
            'name':'Skybind R1 Android-to-Go PM bridge (unqualified diagnostic)'}))
            with self.assertRaisesRegex(module.Blocked,'GO_DIAGNOSTIC_RUN_MISMATCH'):
                module.load_hosted_binary(7,'f'*40,Path(d))
    def test_readonly_contract_always_denies_external(self):
        with tempfile.TemporaryDirectory() as d:
            a=self.args(Path(d));a.bkx_signer='x'*64
            self.assertEqual(module.perform(a),2)
            report=json.loads(next(Path(d).glob('*.json')).read_text())
            self.assertFalse(report['grants_issued'])
            self.assertFalse(report['external_provider_qualified'])
            self.assertFalse(report['m2_m3_device_retests_run'])

if __name__=='__main__':unittest.main()
