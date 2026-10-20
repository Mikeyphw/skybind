"""Offline regression checks for Skybind's single entry-point CI device runner."""
from __future__ import annotations

from argparse import Namespace
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ci_artifacts_device as ci


class CiDeviceTest(unittest.TestCase):
    def test_lane_selection_requires_explicit_known_names(self):
        self.assertEqual(ci.select_lanes(['m2-live,m2-preflight', 'm2-live']),
                         ['m2-live', 'm2-preflight'])
        self.assertEqual(ci.select_lanes([]), [])
        with self.assertRaisesRegex(ci.QualificationError, 'UNKNOWN_TEST_LANE'):
            ci.select_lanes(['../../unsafe.py'])

    def test_partial_pair_rejected(self):
        manifest = {'app': {'sha256': 'a'*64}, 'test_apk': {'sha256': 'b'*64}}
        a = {'present': True, 'sha256': 'a'*64, 'signer': 'c'*64}
        with self.assertRaisesRegex(ci.QualificationError, 'PARTIAL_INSTALLED'):
            ci.installation_preflight({'app': a, 'test_apk': {'present': False}}, manifest, 'c'*64)

    def test_other_signer_refused_before_install(self):
        manifest = {'app': {'sha256': 'a'*64}, 'test_apk': {'sha256': 'b'*64}}
        pair = {k: {'present': True, 'sha256': 'd'*64, 'signer': 'e'*64}
                for k in ('app', 'test_apk')}
        with self.assertRaisesRegex(ci.QualificationError, 'INSTALLED_SIGNER_DIFFERS'):
            ci.installation_preflight(pair, manifest, 'c'*64)

    def test_same_signer_upgrade_or_exact_pair(self):
        manifest = {'app': {'sha256': 'a'*64}, 'test_apk': {'sha256': 'b'*64}}
        pair = {k: {'present': True, 'sha256': x, 'signer': 'c'*64}
                for k, x in [('app', 'a'*64), ('test_apk', 'b'*64)]}
        self.assertEqual(ci.installation_preflight(pair, manifest, 'c'*64), 'MATCHED')
        pair['test_apk']['sha256'] = 'd'*64
        self.assertEqual(ci.installation_preflight(pair, manifest, 'c'*64),
                         'SAME_SIGNER_UPGRADE_NEEDED')
        self.assertEqual(ci.installation_preflight({'app': {'present': False},
                                                    'test_apk': {'present': False}}, manifest, 'c'*64),
                         'ABSENT')

    def test_artifact_cache_symlink_and_extras_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td) / 'pair'
            folder.mkdir()
            (folder / 'rogue.apk').write_bytes(b'no')
            with self.assertRaisesRegex(ci.QualificationError, 'UNEXPECTED_ARTIFACT_MEMBER'):
                ci.safe_folder(folder)
            (folder / 'rogue.apk').unlink()
            (folder / 'app-debug.apk').symlink_to('/tmp')
            with self.assertRaisesRegex(ci.QualificationError, 'UNEXPECTED_ARTIFACT_MEMBER'):
                ci.safe_folder(folder)

    def test_partial_artifact_cache_never_silently_reused(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'pair'
            root.mkdir()
            (root / 'app-debug.apk').write_bytes(b'only one')
            with self.assertRaisesRegex(ci.QualificationError, 'PARTIAL_ARTIFACT_CACHE'):
                ci.obtain_pair(8, 1, root)

    def test_installer_only_signed_update_no_uninstall(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td)
            (f/'app-debug.apk').write_bytes(b'a')
            (f/'app-debug-androidTest.apk').write_bytes(b'b')
            calls = []
            def fake(_serial, *args, **kwargs):
                calls.append(args)
                return Namespace(stdout='Success\n')
            with patch.object(ci.live, 'adb', side_effect=fake):
                ci.install_pair('ABC', f, 'SAME_SIGNER_UPGRADE_NEEDED')
            self.assertEqual([c[:2] for c in calls], [('install', '-r'), ('install', '-r')])
            self.assertIn('-t', calls[1])
            self.assertFalse(any('uninstall' in args or 'clear' in args or '-d' in args
                                 for args in calls))
            with self.assertRaisesRegex(ci.QualificationError, 'INSTALL_NOT_REQUIRED'):
                ci.install_pair('ABC', f, 'MATCHED')

    def test_lane_receipt_cannot_overclaim_release_or_wrong_artifact(self):
        x = dict(schema='skybind-m2-live-v1', state='PASS_M2_L1_LIVE_READ_BROWSE_REBIND',
                 source_sha='a'*40, github_run_id=55, artifact_id=77,
                 installed_pair_verified=True, signing_verified=True,
                 device_qualified=False, release_qualified=False,
                 m2_l1_device_qualified=True, m2_l2_device_qualified=False,
                 qualified_scope='M2-L1_READ_ONLY_APP_ROOTSERVICE_QUERY_BROWSE_REBIND', receipt='/fixture')
        self.assertEqual(ci.validated_lane_receipt(x, lane='m2-live',run_id=55,
                         sha='a'*40,artifact_id=77)['state'], x['state'])
        for change in ({'artifact_id': 42}, {'release_qualified': True},
                       {'source_sha':'b'*40}, {'state':'PASS_M2_L1_PAIR_PREFLIGHT_ONLY'},
                       {'installed_pair_verified':False}):
            with self.assertRaises(ci.QualificationError):
                ci.validated_lane_receipt(x | change, lane='m2-live',run_id=55,
                                          sha='a'*40,artifact_id=77)

    def test_live_product_failure_not_downgraded_to_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'lane.json'
            record = {'schema':'skybind-m2-live-v1', 'state':'FAILED',
                      'reason':'SKYBIND_LIVE_FAILED_BROWSE', 'receipt':str(path)}
            path.write_text(json.dumps(record))
            def runner(_opts):
                print(json.dumps({'state':'FAILED','reason':record['reason'],
                                  'receipt':str(path)}))
                return 2
            with patch.object(ci.live, 'run', side_effect=runner):
                with self.assertRaisesRegex(ci.QualificationError, 'TEST_LANE_FAILED'):
                    ci.execute_lane('m2-live', 8, 'serial-1', Path(td), None, 'a'*40, 55)

    def test_lane_preflight_saved_receipt_round_trip(self):
        # Regression for source ebf261a: previously store() wrote the file
        # BEFORE adding the receipt key, making the launcher always BLOCKED.
        with tempfile.TemporaryDirectory() as td:
            sha = 'a'*40
            record = dict(schema='skybind-m2-live-v1',
                          state='PASS_M2_L1_PAIR_PREFLIGHT_ONLY', reason=None,
                          source_sha=sha, github_run_id=9, artifact_id=17,
                          installed_pair_verified=True, signing_verified=True,
                          device_qualified=False, release_qualified=False,
                          m2_l1_device_qualified=False)
            def fake_lane(opts):
                receipt = ci.live.store(record, dest=Path(td))
                print(json.dumps({k: record.get(k) for k in
                      ('state','reason','receipt','source_sha','github_run_id',
                       'artifact_id','installed_pair_verified','m2_l1_device_qualified')}))
                return 0
            with patch.object(ci.live, 'run', side_effect=fake_lane):
                result = ci.execute_lane('m2-preflight', 9, 'device1', Path(td),
                                         None, sha, 17)
            self.assertEqual(result['state'], 'PASS_M2_L1_PAIR_PREFLIGHT_ONLY')
            self.assertIsNone(result['qualified_scope'])
            persisted = json.loads(Path(result['receipt']).read_text())
            self.assertEqual(persisted['receipt'], result['receipt'])
            self.assertFalse(persisted['device_qualified'])

    def test_lane_missing_receipt_path_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'broken.json'
            body={'state':'BLOCKED','reason':'SKYBIND_LIVE_BLOCKED_ROOT_AUTH'}
            path.write_text(json.dumps(body))
            def fake_lane(opts):
                print(json.dumps(body | {'receipt':str(path)}))
                return 2
            with patch.object(ci.live,'run',side_effect=fake_lane):
                with self.assertRaisesRegex(ci.QualificationError,
                                            'LANE_RECEIPT_PATH_MISMATCH'):
                    ci.execute_lane('m2-live',9,'device1',Path(td),None,'a'*40,17)

    def test_lane_failed_result_is_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            record=dict(schema='skybind-m2-live-v1', state='FAILED',
                        reason='SKYBIND_LIVE_FAILED_BROWSE',
                        source_sha='a'*40,github_run_id=9,artifact_id=17,
                        installed_pair_verified=True,signing_verified=True,
                        device_qualified=False,release_qualified=False,
                        m2_l1_device_qualified=False)
            def fake_lane(opts):
                ci.live.store(record,dest=Path(td))
                print(json.dumps({k:record.get(k) for k in
                      ('state','reason','receipt','source_sha','github_run_id',
                       'artifact_id','installed_pair_verified','m2_l1_device_qualified')}))
                return 2
            with patch.object(ci.live,'run',side_effect=fake_lane):
                with self.assertRaisesRegex(ci.QualificationError,
                                            'TEST_LANE_FAILED:m2-live:SKYBIND_LIVE_FAILED_BROWSE'):
                    ci.execute_lane('m2-live',9,'device1',Path(td),None,'a'*40,17)

    def test_source_gate_rejects_lost_receipt_self_reference(self):
        import ci_artifacts_device_source_gate as gate
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for rel in (gate.CLI,gate.LANE,gate.TESTS,gate.GROUPED):
                dest=root/rel
                dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_text((gate.ROOT/rel).read_text())
            lane=root/gate.LANE
            original=lane.read_text()
            marker="report['receipt'] = str(filename)"
            self.assertIn(marker,original)
            lane.write_text(original.replace(marker,"report['receipt'] = None",1))
            with self.assertRaisesRegex(gate.Violation,
                                        'LIVE_RECEIPT_MUST_PERSIST_SELF_REFERENCE'):
                gate.verify(root)

    def test_existing_pair_no_automatic_test_selection_or_install(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pair = root/'pair'; pair.mkdir()
            for name in ci.FILES: (pair/name).write_bytes(b'fixture')
            signer = 'c'*64
            manifest = {'app': {'sha256':'a'*64}, 'test_apk': {'sha256':'b'*64}}
            record = {'app': {'present':True,'sha256':'a'*64,'signer':signer},
                      'test_apk': {'present':True,'sha256':'b'*64,'signer':signer}}
            args = Namespace(run_id=9, test=[], serial='emulator-5554', remote=None,
                             expected_sha=None, artifact_dir=pair,
                             output_root=root/'receipts', install=False, skip_install=True)
            def adb(serial,*a,**kw):
                if 'ro.build.version.sdk' in a: return Namespace(stdout='36\n')
                if 'getenforce' in a: return Namespace(stdout='Enforcing\n')
                raise AssertionError(f'Unexpected adb action: {a}')
            with patch.object(ci.live, 'current_source', return_value='a'*40), \
                 patch.object(ci.live, 'github', return_value={'id':17,'digest':'sha256:'+'e'*64}), \
                 patch.object(ci, 'obtain_pair', return_value=pair), \
                 patch.object(ci.live, 'read_pin', return_value=signer), \
                 patch.object(ci.live, 'verify_candidate', return_value=manifest), \
                 patch.object(ci.live, 'choose_device', return_value='emulator-5554'), \
                 patch.object(ci.live, 'adb', side_effect=adb), \
                 patch.object(ci, 'installed_identity', return_value=record), \
                 patch.object(ci.live, 'installed_pair', return_value=True), \
                 patch.object(ci, 'install_pair') as install, \
                 patch.object(ci, 'execute_lane') as execute, \
                 patch('sys.stdout', new_callable=io.StringIO):
                code = ci.run(args)
            self.assertEqual(code, 0)
            install.assert_not_called()
            execute.assert_not_called()
            doc = json.loads(next((root/'receipts').rglob('summary.json')).read_text())
            self.assertEqual(doc['status'], 'PASS_CI_PAIR_VERIFIED_NO_TESTS_SELECTED')
            self.assertTrue(doc['installed_pair_verified'])
            self.assertFalse(doc['release_qualified'])
            self.assertFalse(doc['device_qualified'])

    def test_changed_pair_requires_explicit_install(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            args = Namespace(run_id=9,test=[],serial=None,remote=None,expected_sha=None,
                             artifact_dir=root/'pair',output_root=root/'receipts',
                             install=False,skip_install=True)
            manifest={'app': {'sha256':'a'*64}, 'test_apk': {'sha256':'b'*64}}
            with patch.object(ci.live,'current_source',return_value='a'*40), \
                 patch.object(ci.live,'github',return_value={'id':17,'digest':'sha256:'+'e'*64}), \
                 patch.object(ci,'obtain_pair',return_value=root/'pair'), \
                 patch.object(ci.live,'read_pin',return_value='c'*64), \
                 patch.object(ci.live,'verify_candidate',return_value=manifest), \
                 patch.object(ci.live,'choose_device',return_value='emulator-5554'), \
                 patch.object(ci.live,'adb',side_effect=lambda _s,*a,**kw:Namespace(
                     stdout='36' if 'ro.build.version.sdk' in a else 'Enforcing')), \
                 patch.object(ci,'installed_identity',return_value={
                     'app': {'present': False}, 'test_apk':{'present':False}}), \
                 patch.object(ci,'install_pair') as install, \
                 patch('sys.stdout',new_callable=io.StringIO):
                code=ci.run(args)
            self.assertEqual(code,2)
            install.assert_not_called()
            doc=json.loads(next((root/'receipts').rglob('summary.json')).read_text())
            self.assertEqual(doc['reason'],'EXPLICIT_INSTALL_REQUIRED')
            self.assertFalse(doc['installation_performed'])


if __name__ == '__main__':
    unittest.main()
