"""Offline, negative-first NATIVE-06 acceptance contract tests."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MODPATH = ROOT / 'scripts/dev/android/native06_personal_acceptance.py'
sys.path.insert(0, str(MODPATH.parent))
spec = importlib.util.spec_from_file_location('native06_personal_acceptance', MODPATH)
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)

class Native06Tests(unittest.TestCase):
    def test_readonly_without_mutations(self):
        self.assertEqual(tuple(x[0] for x in a.plan('readonly', remote=None,
            consent_config=False, consent_jobs=False, consent_stop=False,
            consent_reconcile=False)), tuple(x[0] for x in a.BASE_LANES))
        self.assertNotIn('mount-lifecycle', [x[0] for x in a.BASE_LANES])

    def test_readonly_rejects_any_unauthorized_write_consent(self):
        for flag in ('consent_config', 'consent_jobs', 'consent_stop', 'consent_reconcile'):
            opts = dict(profile='readonly', remote='photos', consent_config=False,
                        consent_jobs=False, consent_stop=False, consent_reconcile=False)
            opts[flag] = True
            with self.assertRaisesRegex(a.CandidateError, 'READONLY_MUST_NOT'):
                a.plan(**opts)

    def test_full_requires_all_consents(self):
        flags = dict(profile='full', remote='photos', consent_config=True,
                     consent_jobs=True, consent_stop=True, consent_reconcile=True)
        self.assertIn('mount-lifecycle', [x[0] for x in a.plan(**flags)])
        for key in ('remote', 'consent_config', 'consent_jobs', 'consent_stop', 'consent_reconcile'):
            sub = dict(flags)
            sub[key] = None if key == 'remote' else False
            with self.assertRaises(a.CandidateError):
                a.plan(**sub)
        for remote in ('../../../', 'photo space', 'a'*65):
            with self.assertRaises(a.CandidateError):
                a.plan(**{**flags, 'remote': remote})

    def test_full_lanes_include_all_required_privileged_and_negative_checks(self):
        self.assertTrue({'negative-live', 'transport-live', 'mount-lifecycle',
                         'config-disposable', 'm3-check', 'm3-cancel', 'm3-copy',
                         'auto-root', 'cold-relaunch'} <= set(a.REQUIRED_FULL))

    def test_instrumentation_rejects_skipped_failed_or_incomplete(self):
        case = 'NativePersonalLiveTest#automaticForegroundRootNoManualConnect'
        ok = ('INSTRUMENTATION_STATUS: test=automaticForegroundRootNoManualConnect\n'
              'INSTRUMENTATION_STATUS: numtests=1\n'
              'INSTRUMENTATION_STATUS_CODE: 1\n'
              'INSTRUMENTATION_STATUS_CODE: 0\n'
              'OK (1 test)\nINSTRUMENTATION_CODE: -1\n')
        self.assertRegex(a.parse_instrumentation(case, ok, 0), '^[0-9a-f]{64}$')
        for output, rc in ((ok, 1), (ok.replace(' 0\n', ' -3\n'), 0),
                           (ok.replace('OK (1 test)', 'FAILURES!!!'), 0),
                           (ok.replace('test=automatic', 'test=foreign'), 0),
                           (ok.replace('INSTRUMENTATION_CODE: -1', 'INSTRUMENTATION_CODE: 0'), 0),
                           (ok.replace('INSTRUMENTATION_STATUS_CODE: 0\n', ''), 0),
                           (ok+'SKYBIND_LIVE_BLOCKED_DAEMON\n', 0)):
            with self.subTest(rc=rc, output=output[-100:]), self.assertRaises(a.CandidateError):
                a.parse_instrumentation(case, output, rc)

    def fake_manifest(self):
        return dict(source_sha='a'*40, run_id=42, requested_version_code=2,
                    app={'sha256':'1'*64}, test_apk={'sha256':'2'*64})

    def fake_receipt(self):
        return dict(schema=a.SCHEMA, profile='full', status='PASS_NATIVE_PERSONAL_DEVICE_FULL',
                    device_qualified=True, release_qualified=False, owner_approval=False,
                    independent_attestation=False, source_sha='a'*40, github_run_id=42,
                    app_sha256='1'*64, test_sha256='2'*64,
                    signer_sha256='3'*64, candidate_version_code=2,
                    root_manager='kernelsu', device_api=35, device_serial_sha256='9'*64,
                    module={'installed_module_verified': True, 'module_archive_sha256': '7'*64,
                            'module_binary_sha256': '8'*64, 'module_provider':'bclone'},
                    lanes={**{key: {'status':'PASS', 'case': a.CASE+method,
                          'instrumentation_sha256':'0'*64}
                          for key, method, _ in a.BASE_LANES+a.WRITE_LANES},
                           'cold-relaunch':{'status':'PASS','old_pid_sha256':'1'*64,
                                            'new_pid_sha256':'2'*64},
                           'auto-root-after-cold':{'status':'PASS',
                            'case':a.CASE+'NativePersonalLiveTest#automaticForegroundRootNoManualConnect',
                            'instrumentation_sha256':'0'*64}})

    def test_full_receipt_matching_byte_identity_required(self):
        manifest = self.fake_manifest()
        receipt = self.fake_receipt()
        a.checked_full_receipt(receipt, manifest, '3'*64)
        for key, value in [('source_sha', 'b'*40), ('app_sha256', '4'*64),
                           ('test_sha256', '5'*64), ('signer_sha256', '6'*64),
                           ('root_manager', 'unknown'), ('device_api', 25),
                           ('module', None), ('device_serial_sha256','bad'), ('release_qualified', True), ('independent_attestation', True),
                           ('owner_approval', True), ('device_qualified', False),
                           ('status', 'PASS_NATIVE_PERSONAL_READONLY_ONLY_NOT_QUALIFIED')]:
            data = dict(receipt, **{key:value})
            with self.subTest(key=key), self.assertRaises(a.CandidateError):
                a.checked_full_receipt(data, manifest, '3'*64)

    def test_skipped_lane_cannot_be_promoted(self):
        manifest = self.fake_manifest()
        for name in a.REQUIRED_FULL:
            receipt = self.fake_receipt()
            receipt['lanes'] = dict(receipt['lanes'])
            del receipt['lanes'][name]
            with self.subTest(name=name), self.assertRaisesRegex(a.CandidateError, 'LANES_INCOMPLETE'):
                a.checked_full_receipt(receipt, manifest, '3'*64)
        receipt = self.fake_receipt()
        receipt['lanes']['negative-live'] = {'status': 'SKIPPED'}
        with self.assertRaises(a.CandidateError):
            a.checked_full_receipt(receipt, manifest, '3'*64)

    def test_receipt_cannot_replace_exact_test_name_or_remove_log_proof(self):
        manifest = self.fake_manifest()
        receipt = self.fake_receipt()
        for corrupt in ({'case': 'foreign.Test#method'},
                        {'instrumentation_sha256': 'not-a-real-log-digest'},
                        {'status': 'SKIPPED'}):
            data = dict(receipt, lanes={k: dict(v) for k,v in receipt['lanes'].items()})
            data['lanes']['auto-root'].update(corrupt)
            with self.assertRaises(a.CandidateError):
                a.checked_full_receipt(data, manifest, '3'*64)

    def test_app_package_identity_can_never_be_replaced_by_only_checksum(self):
        source = MODPATH.read_text()
        self.assertIn("inspect_installed(serial, manifest, signer)", source)
        self.assertIn("'ALREADY_INSTALLED_IDENTICAL_PAIR'", source)
        self.assertIn("gh_info(manifest['run_id'])", source)
        self.assertNotIn("adb(serial, 'install'", source)
        self.assertNotIn("adb(serial, 'uninstall'", source)

    def test_native06_source_and_lifecycle_safety_contract(self):
        import native06_source_gate
        self.assertEqual(native06_source_gate.check()['status'],
                         'PASS_NATIVE06_ACCEPTANCE_SOURCE_ONLY')

    def test_approval_requires_all_owner_flags(self):
        from argparse import Namespace
        args = Namespace(ui_reviewed=False, root_approved=True, mount_reviewed=True,
                         accept_personal_scope=True, accept_untested_managers=True)
        with self.assertRaises(a.CandidateError):
            a.owner_approve(args)

if __name__ == '__main__':
    unittest.main()
