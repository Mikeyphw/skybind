"""Offline, negative-first NATIVE-06 acceptance contract tests."""
import importlib.util
from pathlib import Path
import sys
import tempfile
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
                    instrumentation_evidence_dir='native06-logs-'+'a'*32,
                    independent_attestation=False, source_sha='a'*40, github_run_id=42,
                    app_sha256='1'*64, test_sha256='2'*64,
                    signer_sha256='3'*64, candidate_version_code=2,
                    root_manager='kernelsu', device_api=36, device_serial_sha256='9'*64,
                    module={'installed_module_verified': True, 'module_archive_sha256': '7'*64,
                            'module_binary_sha256': '8'*64, 'module_provider':'bclone',
                            'active_module_verified': True, 'active_daemon_binary_sha256': '8'*64,
                            'active_daemon_process_count': 1},
                    lanes={**{key: {'status':'PASS', 'case': a.CASE+method,
                          'instrumentation_sha256':'0'*64,
                          'instrumentation_log':'native06-logs-'+'a'*32+'/'+key+'.log'}
                          for key, method, _ in a.BASE_LANES+a.WRITE_LANES},
                           'cold-relaunch':{'status':'PASS','old_pid_sha256':'1'*64,
                                            'new_pid_sha256':'2'*64},
                           'auto-root-after-cold':{'status':'PASS',
                            'case':a.CASE+'NativePersonalLiveTest#automaticForegroundRootNoManualConnect',
                            'instrumentation_sha256':'0'*64,
                          'instrumentation_log':'native06-logs-'+'a'*32+'/auto-root-after-cold.log'}})

    def test_private_instrumentation_log_revalidated_after_approval(self):
        method = 'NativeUiTest#realNavigationHasFiveDistinctPages'
        output = ('INSTRUMENTATION_STATUS: numtests=1\n'
                  'INSTRUMENTATION_STATUS: test=realNavigationHasFiveDistinctPages\n'
                  'INSTRUMENTATION_STATUS_CODE: 1\n'
                  'INSTRUMENTATION_STATUS_CODE: 0\n'
                  'INSTRUMENTATION_RESULT: stream=OK (1 test)\n'
                  'INSTRUMENTATION_CODE: -1\n')
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / ('native06-logs-' + 'a'*32)
            folder.mkdir(mode=0o700)
            file = folder / 'navigation.log'
            file.write_text(output)
            file.chmod(0o600)
            doc = {'lanes': {'navigation': {'case': a.CASE + method,
                   'instrumentation_log': folder.name + '/' + file.name,
                   'instrumentation_sha256': a.sha256_bytes(output.encode())}}}
            a.verify_instrumentation_logs(doc, Path(tmp))
            file.write_text(output.replace('realNavigationHasFiveDistinctPages', 'foreignCase'))
            with self.assertRaisesRegex(a.CandidateError, 'INSTRUMENTATION_LOG_DIGEST_MISMATCH'):
                a.verify_instrumentation_logs(doc, Path(tmp))
            file.write_text(output)
            file.chmod(0o644)
            with self.assertRaisesRegex(a.CandidateError, 'INSTRUMENTATION_LOG_MISSING_OR_UNSAFE'):
                a.verify_instrumentation_logs(doc, Path(tmp))
            file.chmod(0o600)
            doc['lanes']['navigation']['instrumentation_sha256'] = a.sha256_bytes(output.encode())
            doc['lanes']['navigation']['case'] = a.CASE + 'NativeUiTest#foreignCase'
            with self.assertRaisesRegex(a.CandidateError, 'INSTRUMENTATION_FAILED_OR_SKIPPED'):
                a.verify_instrumentation_logs(doc, Path(tmp))

    def test_full_receipt_matching_byte_identity_required(self):
        manifest = self.fake_manifest()
        receipt = self.fake_receipt()
        a.checked_full_receipt(receipt, manifest, '3'*64)
        for key, value in [('source_sha', 'b'*40), ('app_sha256', '4'*64),
                           ('test_sha256', '5'*64), ('signer_sha256', '6'*64),
                           ('root_manager', 'unknown'), ('device_api', 35),
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

    def test_active_daemon_source_must_match_module(self):
        receipt = self.fake_receipt()
        for invalid in (
            {'active_module_verified': False},
            {'active_daemon_binary_sha256': '0'*64},
            {'active_daemon_process_count': 0},
            {'active_daemon_process_count': 9},
            {'active_daemon_process_count': '1'},
        ):
            doc = {**receipt, 'module': {**receipt['module'], **invalid}}
            with self.subTest(invalid=invalid), self.assertRaisesRegex(a.CandidateError,
                    'SAME_SOURCE_INSTALLED_MODULE_EVIDENCE_MISSING'):
                a.checked_full_receipt(doc, self.fake_manifest(), '3'*64)

    def test_disposable_directory_has_exact_identity(self):
        name, dest = a.mount_fixture_identity()
        self.assertRegex(name, r'^NativeLife[0-9a-f]{12}$')
        self.assertEqual(dest, '/storage/emulated/0/Download/.skybind-native-' + name)
        with self.assertRaisesRegex(a.CandidateError, 'MOUNT_FIXTURE_PATH_UNSAFE'):
            a.prepare_mount_fixture('emulator-5554', name, dest + '/unsafe')
        with self.assertRaisesRegex(a.CandidateError, 'MOUNT_FIXTURE_CLEANUP_PATH_UNSAFE'):
            a.remove_mount_fixture('emulator-5554', name, '/storage/emulated/0/Download')

    def test_disposable_fixture_guards_and_nondestructive_cleanup(self):
        from subprocess import CompletedProcess
        name = 'NativeLife' + 'a'*12
        dest = '/storage/emulated/0/Download/.skybind-native-' + name
        executed = []
        def fake(serial, *args):
            executed.append(args)
            if args[:2] == ('test', '-d') or args[0] == 'mkdir': rc = 0
            elif args[:2] in (('test', '-e'), ('test', '-L')): rc = 1
            elif args[0] == 'rmdir': rc = 0
            elif args[0] == 'ls': rc = 0
            else: raise AssertionError(args)
            return CompletedProcess(args, rc, '', '')
        with patch.object(a, 'mount_fixture_shell', fake):
            a.prepare_mount_fixture('emulator-5554', name, dest)
            a.remove_mount_fixture('emulator-5554', name, dest)
        self.assertIn(('mkdir',dest), executed)
        self.assertIn(('rmdir',dest), executed)
        self.assertFalse(any('rm' in args or 'su' in args for args in executed))
        def collision(serial,*args):
            return CompletedProcess(args,0,'','')
        with patch.object(a, 'mount_fixture_shell', collision):
            with self.assertRaisesRegex(a.CandidateError, 'MOUNT_FIXTURE_PATH_ALREADY_PRESENT'):
                a.prepare_mount_fixture('emulator-5554',name,dest)
        def denied(serial,*args):
            return CompletedProcess(args,1,'','')
        with patch.object(a, 'mount_fixture_shell', denied):
            with self.assertRaisesRegex(a.CandidateError, 'MOUNT_FIXTURE_CLEANUP_FAILED'):
                a.remove_mount_fixture('emulator-5554',name,dest)

    def test_app_header_has_explicit_android_status_bar_inset(self):
        ui = (ROOT / 'android-app/app/src/main/java/io/github/mikeyphw/skybind/ui/SkybindApp.kt').read_text()
        self.assertIn('Modifier.statusBarsPadding().testTag("app-header")', ui)
        self.assertIn('Scaffold(', ui)

    def test_resume_auto_root_only_after_authenticated_background_disconnect(self):
        source = (ROOT / 'android-app/app/src/main/java/io/github/mikeyphw/skybind/bridge/SkybindSessionViewModel.kt').read_text()
        self.assertIn('resumeReconnectPending = !foreground && snapshot.online', source)
        self.assertIn('resumeReconnectPending && snapshot.link == LinkState.DISCONNECTED', source)
        self.assertIn('resumeReconnectPending = false', source)

    def test_lifecycle_instrumentation_uses_prepared_host_mountpoint(self):
        source = (ROOT / 'android-app/app/src/androidTest/java/io/github/mikeyphw/skybind/NativePersonalLiveTest.kt').read_text()
        self.assertIn('"skybind.native.personal.mountname"', source)
        self.assertIn('"skybind.native.personal.mountpoint"', source)
        self.assertIn('mountpoint = mountpoint,', source)
        self.assertNotIn('UUID.randomUUID()', source)

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
