"""M2-L2 real UI device-lane evidence, scoped receipts and source negatives."""
from pathlib import Path
import importlib.util
import tempfile
import unittest
from unittest.mock import patch
import json
import io
from contextlib import redirect_stdout

ROOT = Path(__file__).resolve().parents[1]
def load(rel, name):
    spec=importlib.util.spec_from_file_location(name,ROOT/rel)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module
source=load('scripts/dev/android/m2_ui_live_source_gate.py','ui_source_gate')
worker=load('scripts/dev/android/m2_live_device.py','ui_live_worker')
ci=load('scripts/devtool/ci_artifacts_device.py','ui_ci')

GOOD='''INSTRUMENTATION_STATUS: class=io.github.mikeyphw.skybind.LiveUiAcceptanceTest
INSTRUMENTATION_STATUS: numtests=1
INSTRUMENTATION_STATUS: test=liveUiReadOnlyNavigationRecovery
INSTRUMENTATION_STATUS_CODE: 1
INSTRUMENTATION_STATUS: test=liveUiReadOnlyNavigationRecovery
INSTRUMENTATION_STATUS_CODE: 0
INSTRUMENTATION_RESULT: stream=OK (1 test)
INSTRUMENTATION_CODE: -1
'''

class UiLiveGate(unittest.TestCase):
    def test_source(self):
        self.assertEqual(source.verify(ROOT)['state'],'PASS_M2_L2_LIVE_UI_SOURCE_ONLY')

    def test_hosted_compose_kotlin_compile_contract_regression(self):
        # GitHub Actions run 39360456956: fail closed on the five previous
        # AndroidTest compiler errors, without running a local APK build.
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            needed=(source.UI_TEST,source.VM,source.APP,source.ACTIVITY,
                    source.CI,source.RUNNER,source.GROUPED,source.BROWSER_TEST)
            for rel in needed:
                target=root/rel;target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes((ROOT/rel).read_bytes())
            self.assertEqual(source.verify(root)['state'],'PASS_M2_L2_LIVE_UI_SOURCE_ONLY')
            ui_path=root/source.UI_TEST
            original_ui=ui_path.read_text()
            ui_path.write_text(original_ui.replace(
                'import androidx.compose.ui.semantics.getOrNull\n',
                'import androidx.compose.ui.test.onAllNodes\n',1))
            with self.assertRaisesRegex(source.Violation,
                                        'M2_L2_COMPOSE_SEMANTICS_IMPORTS_INVALID'):
                source.verify(root)
            ui_path.write_text(original_ui)
            browse_path=root/source.BROWSER_TEST
            original_browser=browse_path.read_text()
            browse_path.write_text(original_browser.replace(
                'browser = BrowserState(', 'BrowserState(',1))
            with self.assertRaisesRegex(source.Violation,
                                        'M2_L2_BROWSER_FIXTURE_NAMED_BROWSER_REQUIRED'):
                source.verify(root)

    def test_exact_single_case(self):
        self.assertEqual(worker.parse_ui_live(GOOD),('PASS_M2_L2_LIVE_UI_READONLY_RECOVERY', None))
        for bad in (GOOD.replace('INSTRUMENTATION_CODE: -1',''),
                    GOOD.replace('INSTRUMENTATION_STATUS_CODE: 0','INSTRUMENTATION_STATUS_CODE: 0\nINSTRUMENTATION_STATUS_CODE: 0'),
                    GOOD.replace('numtests=1','numtests=2'),
                    GOOD.replace('test=liveUiReadOnlyNavigationRecovery','test=wrongTest')):
            with self.subTest(bad=bad[-50:]):
                self.assertEqual(worker.parse_ui_live(bad)[0],'FAILED')

    def test_permission_block_and_no_folder_are_not_failures(self):
        for reason in worker.UI_BLOCKED:
            with self.subTest(reason=reason):
                out=GOOD.replace('INSTRUMENTATION_STATUS_CODE: 0',
                                 'INSTRUMENTATION_STATUS: stack='+reason+'\nINSTRUMENTATION_STATUS_CODE: -2')
                self.assertEqual(worker.parse_ui_live(out),('BLOCKED',reason))

    def test_browse_and_disconnect_regressions_are_failures(self):
        for reason in worker.UI_FAILED:
            with self.subTest(reason=reason):
                out=GOOD.replace('INSTRUMENTATION_STATUS_CODE: 0',
                                 'INSTRUMENTATION_STATUS: stack='+reason+'\nINSTRUMENTATION_STATUS_CODE: -2')
                self.assertEqual(worker.parse_ui_live(out),('FAILED',reason))

    def test_lanes_explicitly_registered(self):
        self.assertEqual(ci.LANES['m2-ui-live'],'ui-live')
        self.assertEqual(ci.select_lanes(['m2-ui-live']),['m2-ui-live'])
        self.assertEqual(ci.select_lanes([]),[])

    def test_new_lane_narrow_evidence(self):
        receipt=dict(schema='skybind-m2-live-v1',source_sha='a'*40,github_run_id=17,
                     artifact_id=19,installed_pair_verified=True, signing_verified=True,
                     release_qualified=False,device_qualified=False,m2_l1_device_qualified=False,
                     m2_l2_device_qualified=True,state='PASS_M2_L2_LIVE_UI_READONLY_RECOVERY',
                     qualified_scope='M2-L2_REAL_COMPOSE_UI_BROWSE_DISCONNECT_RECONNECT',receipt='/tmp/dummy')
        x=ci.validated_lane_receipt(receipt,lane='m2-ui-live',run_id=17,sha='a'*40,artifact_id=19)
        self.assertEqual(x['qualified_scope'],receipt['qualified_scope'])
        for change in ({'m2_l1_device_qualified':True},{'m2_l2_device_qualified':False},
                       {'release_qualified':True},{'artifact_id':30},{'source_sha':'b'*40},
                       {'qualified_scope':'M2-L1_READ_ONLY_APP_ROOTSERVICE_QUERY_BROWSE_REBIND'}):
            with self.subTest(change=change),self.assertRaises(ci.QualificationError):
                ci.validated_lane_receipt(receipt | change,lane='m2-ui-live',run_id=17,sha='a'*40,artifact_id=19)
        # A genuine M2-L1 report must not be repurposed as M2-L2.
        previous=receipt | dict(state='PASS_M2_L1_LIVE_READ_BROWSE_REBIND',
                                m2_l1_device_qualified=True,m2_l2_device_qualified=False,
                                qualified_scope='M2-L1_READ_ONLY_APP_ROOTSERVICE_QUERY_BROWSE_REBIND')
        self.assertEqual(ci.validated_lane_receipt(previous,lane='m2-live',run_id=17,sha='a'*40,artifact_id=19)['state'],
                         'PASS_M2_L1_LIVE_READ_BROWSE_REBIND')
        with self.assertRaises(ci.QualificationError):
            ci.validated_lane_receipt(previous,lane='m2-ui-live',run_id=17,sha='a'*40,artifact_id=19)

    def test_source_guard_rejects_fixture_backend_and_lost_disconnect(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            needed=(source.UI_TEST,source.VM,source.APP,source.ACTIVITY,source.CI,source.RUNNER,source.GROUPED,source.BROWSER_TEST)
            for rel in needed:
                target=root/rel;target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes((ROOT/rel).read_bytes())
            original=(root/source.UI_TEST).read_text()
            (root/source.UI_TEST).write_text(original.replace('compose.activityRule.scenario.recreate()',
                                                              '/* removed */'))
            with self.assertRaisesRegex(source.Violation,'LIVE_UI_CONTRACT_MISSING'):
                source.verify(root)
            (root/source.UI_TEST).write_text(original)
            vm=root/source.VM
            vm.write_text(vm.read_text().replace('bridge.close()', '/* disconnected without unbind */'))
            with self.assertRaisesRegex(source.Violation,'VM_DISCONNECT_MISSING'):
                source.verify(root)

    def test_isolated_live_ui_runner_produces_narrow_receipt(self):
        from argparse import Namespace
        from subprocess import CompletedProcess
        with tempfile.TemporaryDirectory() as td:
            calls=[]
            def fake_adb(serial,*argv,**kwargs):
                calls.append(argv)
                if 'getprop' in argv: return CompletedProcess(argv,0,'36\n','')
                if 'getenforce' in argv: return CompletedProcess(argv,0,'Enforcing\n','')
                if 'instrument' in argv: return CompletedProcess(argv,0,GOOD,'')
                raise AssertionError('unreviewed adb command')
            origin_store=worker.store
            with patch.object(worker,'current_source',return_value='a'*40), \
                 patch.object(worker,'github',return_value={'id':19,'digest':'sha256:'+'c'*64}), \
                 patch.object(worker,'verify_candidate',return_value={'app':{'sha256':'b'*64},'test_apk':{'sha256':'d'*64}}), \
                 patch.object(worker,'read_pin',return_value='e'*64), \
                 patch.object(worker,'choose_device',return_value='emulator-5554'), \
                 patch.object(worker,'installed_pair',return_value=True), \
                 patch.object(worker,'adb',side_effect=fake_adb), \
                 patch.object(worker,'store',side_effect=lambda doc:origin_store(doc,dest=Path(td))):
                out=io.StringIO()
                with redirect_stdout(out):
                    status=worker.run(Namespace(run_id=17,mode='ui-live',serial='emulator-5554',
                                                remote=None,artifact_dir=Path(td)))
            self.assertEqual(status,0)
            summary=json.loads(out.getvalue())
            self.assertTrue(summary['m2_l2_device_qualified'])
            self.assertFalse(summary['m2_l1_device_qualified'])
            stored=json.loads(Path(summary['receipt']).read_text())
            self.assertEqual(stored['qualified_scope'],
                             'M2-L2_REAL_COMPOSE_UI_BROWSE_DISCONNECT_RECONNECT')
            self.assertFalse(stored['device_qualified'])
            self.assertFalse(stored['release_qualified'])
            self.assertFalse(stored['root_grant_changed_by_runner'])
            self.assertFalse(stored['daemon_mutated'])
            assert len([x for x in calls if 'instrument' in x]) == 1
            instr=[x for x in calls if 'instrument' in x][0]
            self.assertIn('skybind.ui.live',instr)
            self.assertIn(worker.UI_CASE,instr)
            self.assertNotIn('skybind.live',instr)

    def test_outer_launcher_reads_real_saved_ui_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            sha='a'*40
            record=dict(schema='skybind-m2-live-v1',
                        state='PASS_M2_L2_LIVE_UI_READONLY_RECOVERY',reason=None,
                        source_sha=sha,github_run_id=17,artifact_id=19,
                        installed_pair_verified=True,signing_verified=True,
                        device_qualified=False,release_qualified=False,
                        m2_l1_device_qualified=False,m2_l2_device_qualified=True,
                        qualified_scope='M2-L2_REAL_COMPOSE_UI_BROWSE_DISCONNECT_RECONNECT')
            def fake_run(opts):
                worker.store(record,dest=Path(td))
                print(json.dumps({key:record.get(key) for key in (
                    'state','reason','receipt','source_sha','github_run_id',
                    'artifact_id','installed_pair_verified',
                    'm2_l1_device_qualified','m2_l2_device_qualified')}))
                return 0
            with patch.object(ci.live,'run',side_effect=fake_run):
                result=ci.execute_lane('m2-ui-live',17,'emulator-5554',Path(td),None,sha,19)
            self.assertEqual(result['state'],record['state'])
            self.assertEqual(result['receipt'],record['receipt'])
            self.assertEqual(result['qualified_scope'],record['qualified_scope'])

    def test_receipt_rejects_skip(self):
        v=GOOD.replace('INSTRUMENTATION_STATUS_CODE: 0','INSTRUMENTATION_STATUS_CODE: -3')
        self.assertEqual(worker.parse_ui_live(v)[0],'BLOCKED')

if __name__=='__main__':unittest.main()
