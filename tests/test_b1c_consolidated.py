import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/dev/android'))
import r1_b1c_consolidated_device as gate


class ConsolidatedSecurityContract(unittest.TestCase):
    def test_four_cases_exhaustive(self):
        pieces = []
        for klass, method in sorted(gate.CASES):
            pieces += [f'INSTRUMENTATION_STATUS: class={klass}',
                       f'INSTRUMENTATION_STATUS: test={method}',
                       'INSTRUMENTATION_STATUS_CODE: 0']
        pieces.append('INSTRUMENTATION_CODE: -1')
        result = gate.parse_four_cases('\n'.join(pieces))
        self.assertEqual(len(result), 4)
        self.assertEqual(set(result.values()), {'PASS'})

    def test_incomplete_and_extra_are_denied(self):
        raw = 'INSTRUMENTATION_STATUS: class=bad\nINSTRUMENTATION_STATUS: test=evil\nINSTRUMENTATION_STATUS_CODE: 0\nINSTRUMENTATION_CODE: -1'
        with self.assertRaises(gate.b1c.Blocked):
            gate.parse_four_cases(raw)
        with self.assertRaises(gate.b1c.Blocked):
            gate.parse_four_cases('INSTRUMENTATION_CODE: -1')

    def test_attestation_rejects_legacy_or_wrong_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(gate, 'ROOT', pathlib.Path(tmp)):
                with self.assertRaises(gate.b1c.Blocked):
                    gate.verified_new_attestation('be9ee025156643fe9a5c21d577dd0d2f', gate.b1c.SOURCE)

    def test_source_files_do_not_expose_binder_authority(self):
        manifest = (ROOT / 'android-app/app/src/main/AndroidManifest.xml').read_text()
        gate_src = (ROOT / 'android-app/app/src/main/java/io/github/mikeyphw/skybind/security/BinderCallerGate.kt').read_text()
        self.assertNotIn('BinderCallerGate', manifest)
        self.assertNotIn('exported="true"', manifest.replace('android:exported="true"',''))
        self.assertIn('Binder.getCallingUid()', gate_src)
        self.assertNotIn('issueGrant', gate_src)
        self.assertNotIn('createSocket', gate_src)


if __name__ == '__main__': unittest.main()

class AttestationNegativeMatrix(unittest.TestCase):
    BASE = {
        'status': 'PASS_HOSTED_PAIR_INSPECTED_NOT_DEVICE_QUALIFIED',
        'repository': 'Mikeyphw/skybind',
        'head_sha': 'a'*64, 'device_qualified': False,
        'release_qualified': False, 'github_run_authenticated': True,
        'signatures_inspected': True,
        'app_sha256': '1'*64, 'test_sha256': '2'*64,
        'artifact_zip_sha256': '3'*64, 'debug_signer_sha256': '4'*64,
        'run_id': 77, 'run_attempt': 1, 'artifact_id': 99,
    }
    def fixture(self, overrides=None):
        r = self.BASE.copy()
        r.update(overrides or {})
        return r
    def check(self, receipt):
        pipeline='b'*32
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'build/evidence/r1-android-hosted' / pipeline
            path.mkdir(parents=True)
            (path/'attestation.json').write_text(json.dumps(receipt))
            with patch.object(gate, 'ROOT', pathlib.Path(tmp)):
                return gate.verified_new_attestation(pipeline, 'a'*64)
    def test_good_attestation(self):
        self.assertEqual(self.check(self.fixture())['run_id'], 77)
    def test_reject_status_and_source_drift(self):
        for case in [{'status': 'FAILED_OR_BLOCKED'}, {'head_sha':'c'*64},
                     {'repository':'other/repo'}, {'device_qualified':True},
                     {'release_qualified':True}, {'github_run_authenticated':False},
                     {'signatures_inspected':False}]:
            with self.subTest(case=case), self.assertRaises(gate.b1c.Blocked):
                self.check(self.fixture(case))
    def test_reject_broken_provenance_types(self):
        for case in [{'app_sha256':'xx'}, {'debug_signer_sha256':None},
                     {'run_id': True}, {'artifact_id':0}, {'run_attempt': False}]:
            with self.subTest(case=case), self.assertRaises(gate.b1c.Blocked):
                self.check(self.fixture(case))
    def test_reject_reused_legacy_source_even_for_new_pipeline(self):
        with self.assertRaises(gate.b1c.Blocked):
            gate.verified_new_attestation(gate.b1c.PIPELINE, gate.b1c.SOURCE)
