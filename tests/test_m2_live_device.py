"""M2-L1 negative evidence: source guard + fail-closed instrumentation parser."""
import importlib.util
from pathlib import Path
import json
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

def load(rel, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

source = load('scripts/dev/android/m2_live_source_gate.py', 'live_source')
device = load('scripts/dev/android/m2_live_device.py', 'live_device')

class LiveDeviceEvidence(unittest.TestCase):
    GOOD = '''INSTRUMENTATION_STATUS: class=io.github.mikeyphw.skybind.LiveRootBrowserAcceptanceTest
INSTRUMENTATION_STATUS: numtests=1
INSTRUMENTATION_STATUS: test=liveReadBrowseAndReconnect
INSTRUMENTATION_STATUS_CODE: 1
INSTRUMENTATION_STATUS: test=liveReadBrowseAndReconnect
INSTRUMENTATION_STATUS_CODE: 0
INSTRUMENTATION_RESULT: stream=OK (1 test)
INSTRUMENTATION_CODE: -1
'''

    def test_source_verified(self):
        self.assertEqual(source.verify(ROOT)['state'], 'PASS_M2_L1_LIVE_ACCEPTANCE_SOURCE_ONLY')

    def test_complete_one_case_only(self):
        self.assertEqual(device.parse_live(self.GOOD)[0], 'PASS_M2_L1_LIVE_READ_BROWSE_REBIND')

    def test_missing_final_status_rejected(self):
        self.assertEqual(device.parse_live(self.GOOD.replace('INSTRUMENTATION_CODE: -1', ''))[0], 'FAILED')

    def test_doubled_pass_rejected(self):
        self.assertEqual(device.parse_live(self.GOOD.replace('INSTRUMENTATION_STATUS_CODE: 0',
            'INSTRUMENTATION_STATUS_CODE: 0\nINSTRUMENTATION_STATUS_CODE: 0'))[0], 'FAILED')

    def test_declared_skip_rejected(self):
        self.assertEqual(device.parse_live(self.GOOD.replace('INSTRUMENTATION_STATUS_CODE: 0',
            'INSTRUMENTATION_STATUS_CODE: -3'))[0], 'BLOCKED')

    def test_root_auth_blocks_not_passes(self):
        broken = self.GOOD.replace('INSTRUMENTATION_STATUS_CODE: 0',
            'INSTRUMENTATION_STATUS: stack=SKYBIND_LIVE_BLOCKED_ROOT_BIND\nINSTRUMENTATION_STATUS_CODE: -2')
        self.assertEqual(device.parse_live(broken), ('BLOCKED','SKYBIND_LIVE_BLOCKED_ROOT_BIND'))

    def test_remote_browse_failure_rejected(self):
        broken = self.GOOD.replace('INSTRUMENTATION_STATUS_CODE: 0',
            'INSTRUMENTATION_STATUS: stack=SKYBIND_LIVE_FAILED_BROWSE\nINSTRUMENTATION_STATUS_CODE: -2')
        self.assertEqual(device.parse_live(broken), ('FAILED','SKYBIND_LIVE_FAILED_BROWSE'))

    def test_remote_selection_validated(self):
        self.assertIsNotNone(device.PATTERN.fullmatch('alpha_remote'))
        for name in ('../bad', '/root', 'alpha:secret', 'a/b', 'a'*65, ''):
            self.assertIsNone(device.PATTERN.fullmatch(name))

    def test_device_multiple_requires_serial(self):
        from unittest.mock import patch
        from subprocess import CompletedProcess
        multi=CompletedProcess([], 0, 'List of devices attached\nA\tdevice\nB\tdevice\n', '')
        with patch.object(device.shutil, 'which', return_value='/bin/adb'), \
             patch.object(device, 'invoke', return_value=multi):
            with self.assertRaises(device.Blocked):device.choose_device(None)
            self.assertEqual(device.choose_device('B'), 'B')

    def test_negative_source_no_opt_in(self):
        self.negative(source.KOTLIN, 'assumeTrue("SKYBIND_LIVE_NOT_REQUESTED"',
                      'assumeTrue("REMOVED_GUARD"')

    def test_negative_source_no_reconnect(self):
        self.negative(source.KOTLIN, 'SKYBIND_LIVE_FAILED_RECONNECT_SNAPSHOT',
                      'MISSING_RECONNECT_CHECK')

    def test_negative_runner_live_flag(self):
        self.negative(source.RUNNER, "'-e', 'skybind.live', 'true'",
                      "'-e', 'skybind.live', 'false'")

    def test_preflight_does_not_claim_product_or_live_device_qualification(self):
        result = self.simulated_run('preflight', '')
        self.assertEqual(result['state'], 'PASS_M2_L1_PAIR_PREFLIGHT_ONLY')
        self.assertFalse(result['m2_l1_device_qualified'])
        self.assertFalse(result['device_qualified'])
        self.assertFalse(result['github_run_authenticated'])

    def test_live_single_case_pass_is_narrowly_qualified(self):
        result = self.simulated_run('live', self.GOOD)
        self.assertEqual(result['state'], 'PASS_M2_L1_LIVE_READ_BROWSE_REBIND')
        self.assertTrue(result['m2_l1_device_qualified'])
        self.assertFalse(result['device_qualified'])
        self.assertFalse(result['release_qualified'])
        self.assertFalse(result['installed_apks_modified'])

    def test_receipt_contains_own_path_and_is_immutable(self):
        with tempfile.TemporaryDirectory() as td:
            original = dict(schema='skybind-m2-live-v1', state='BLOCKED',
                            reason='SKYBIND_LIVE_BLOCKED_ROOT_AUTH',
                            device_qualified=False, release_qualified=False,
                            m2_l1_device_qualified=False)
            path = device.store(original, dest=Path(td))
            saved = json.loads(Path(path).read_text())
            self.assertEqual(saved['receipt'], path)
            self.assertEqual(original['receipt'], path)
            self.assertEqual(saved['reason'], original['reason'])
            self.assertFalse(saved['m2_l1_device_qualified'])
            self.assertEqual(len(list(Path(td).glob('m2-live-*.json'))), 1)

    def test_live_root_denial_is_blocked_not_qualified(self):
        broken = self.GOOD.replace('INSTRUMENTATION_STATUS_CODE: 0',
          'INSTRUMENTATION_STATUS: stack=SKYBIND_LIVE_BLOCKED_ROOT_AUTH\nINSTRUMENTATION_STATUS_CODE: -2')
        result = self.simulated_run('live', broken)
        self.assertEqual(result['state'], 'BLOCKED')
        self.assertFalse(result['m2_l1_device_qualified'])

    def simulated_run(self, mode, log):
        from unittest.mock import patch
        from argparse import Namespace
        from subprocess import CompletedProcess
        import hashlib
        manifest = {'app':{'sha256':'a'*64}, 'test_apk':{'sha256':'b'*64}}
        run_id=3
        kwargs=Namespace(run_id=run_id, mode=mode, remote=None,
                         serial=None, artifact_dir=Path('/nonexistent/fixture'))
        returned=[]
        def shell(serial,*args,**kw):
            if 'ro.build.version.sdk' in args: return CompletedProcess([],0,'36\n','')
            if 'getenforce' in args: return CompletedProcess([],0,'Enforcing\n','')
            return CompletedProcess([],0,log,'')
        with patch.object(device,'current_source',return_value='a'*40), \
             patch.object(device,'github',return_value={'id':8,'digest':'sha256:'+'f'*64}), \
             patch.object(device,'verify_candidate',return_value=manifest), \
             patch.object(device,'read_pin',return_value='c'*64), \
             patch.object(device,'choose_device',return_value='emulator-5554'), \
             patch.object(device,'adb',side_effect=shell), \
             patch.object(device,'installed_pair',return_value=True), \
             patch.object(device,'store',side_effect=lambda report: returned.append(dict(report)) or '/receipt'):
            code=device.run(kwargs)
        self.assertEqual(len(returned),1)
        self.assertEqual(code,0 if returned[0]['state'].startswith('PASS_') else 2)
        return returned[0]

    def negative(self, path, before, after):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for relative in (source.KOTLIN, source.RUNNER, source.GROUPED):
                dest = root / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT/relative, dest)
            target = root / path
            content = target.read_text()
            self.assertIn(before, content)
            target.write_text(content.replace(before,after,1))
            with self.assertRaises(source.Violation):source.verify(root)

if __name__ == '__main__':unittest.main()
