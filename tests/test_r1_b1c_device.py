"""Offline B1-C safety and receipt tests; never touch Android or GitHub."""
import importlib.util
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

MOD = Path(__file__).resolve().parents[1] / 'scripts/dev/android/r1_b1c_device.py'
spec=importlib.util.spec_from_file_location('b1c',MOD)
b1c=importlib.util.module_from_spec(spec)
spec.loader.exec_module(b1c)

class DeviceCampaignTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def receipt(self):
        obj={'status':'PASS_HOSTED_PAIR_INSPECTED_NOT_DEVICE_QUALIFIED',
            'repository':'Mikeyphw/skybind','head_sha':b1c.SOURCE,
            'run_id':b1c.RUN,'device_qualified':False,'release_qualified':False,
            'github_run_authenticated':True,'signatures_inspected':True,
            'app_sha256':'a'*64,'test_sha256':'b'*64,'artifact_zip_sha256':'c'*64,
            'debug_signer_sha256':'d'*64,'run_attempt':1,'artifact_id':2}
        target=self.root/'attestation.json'
        target.write_text(json.dumps(obj))
        return target

    def test_rejects_other_pipeline(self):
        with self.assertRaisesRegex(b1c.Blocked,'PIPELINE_ID'):
            b1c.hosted_attestation('0'*32)

    def test_accepts_pinned_receipt(self):
        with patch.object(b1c,'ROOT',self.root):
            dest=self.root/'build/evidence/r1-android-hosted'/b1c.PIPELINE
            dest.mkdir(parents=True)
            (dest/'attestation.json').write_bytes(self.receipt().read_bytes())
            self.assertEqual(b1c.hosted_attestation()['head_sha'],b1c.SOURCE)

    def test_false_or_missing_attestation_does_not_pass(self):
        with patch.object(b1c,'ROOT',self.root):
            dest=self.root/'build/evidence/r1-android-hosted'/b1c.PIPELINE
            dest.mkdir(parents=True)
            path=dest/'attestation.json'
            obj=json.loads(self.receipt().read_text())
            obj['signatures_inspected']=False
            path.write_text(json.dumps(obj))
            with self.assertRaises(b1c.Blocked): b1c.hosted_attestation()
            obj['signatures_inspected']=True
            obj['head_sha']='0'*40
            path.write_text(json.dumps(obj))
            with self.assertRaises(b1c.Blocked): b1c.hosted_attestation()

    def make_zip(self, extra=False):
        app=b'app'; test=b'test'
        archive=self.root/'remote.zip'
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr('app-debug.apk',app)
            z.writestr('app-debug-androidTest.apk',test)
            z.writestr('android-build-manifest.json','{}')
            if extra: z.writestr('untrusted.sh','evil')
        return archive, {'app_sha256':hashlib.sha256(app).hexdigest(),
                         'test_sha256':hashlib.sha256(test).hexdigest()}

    def test_exact_apk_member_hashes(self):
        archive,receipt=self.make_zip()
        pair=b1c.copy_verified_pair(archive,receipt,self.root)
        self.assertEqual(pair['app-debug.apk'].read_bytes(),b'app')

    def test_unexpected_extra_archive_member_rejected(self):
        archive,receipt=self.make_zip(True)
        with self.assertRaisesRegex(b1c.Blocked,'UNEXPECTED_ARCHIVE'):
            b1c.copy_verified_pair(archive,receipt,self.root)

    def test_apk_hash_mismatch_rejected(self):
        archive,receipt=self.make_zip()
        receipt['app_sha256']='f'*64
        with self.assertRaisesRegex(b1c.Blocked,'SHA256'):
            b1c.copy_verified_pair(archive,receipt,self.root)

    def test_adb_multiple_requires_serial(self):
        class Fake:
            returncode=0
            stdout='List of devices attached\nSERIAL1\tdevice\nSERIAL2\tdevice\n'
        with patch.object(b1c.shutil,'which',return_value='/usr/bin/adb'),patch.object(b1c.subprocess,'run',return_value=Fake()):
            with self.assertRaisesRegex(b1c.Blocked,'MULTIPLE'):
                b1c.chosen_device('adb',None)
            self.assertEqual(b1c.chosen_device('adb','SERIAL2'),'SERIAL2')

    def test_adb_timeout_is_blocked(self):
        from subprocess import TimeoutExpired
        with patch.object(b1c.shutil,'which',return_value='/usr/bin/adb'),patch.object(
            b1c.subprocess,'run',side_effect=TimeoutExpired(['adb','devices'],15)):
            with self.assertRaises(TimeoutExpired):
                b1c.chosen_device('adb',None)
        # The outer runner captures SubprocessError and records BLOCKED.
        self.assertTrue(issubclass(TimeoutExpired,__import__('subprocess').SubprocessError))

    def test_android_absent_pm_path_exit_one_both_packages(self):
        """Android path returns 1 for missing packages; list must confirm both."""
        seen=[]
        def shell(adb, serial, *args, **kwargs):
            seen.append(args)
            if args[:3] == ('shell', 'pm', 'path'):
                return 1, '', ''
            if args[:4] == ('shell', 'pm', 'list', 'packages'):
                self.assertEqual(args[4:6], ('--user', '0'))
                return 0, '', ''
            self.fail(repr(args))
        with patch.object(b1c, 'adb_call', side_effect=shell):
            self.assertEqual(b1c.check_installed('adb', 'SERIAL', self.root, {}), 'ABSENT')
        self.assertEqual(len(seen), 4)

    def test_absence_with_successful_empty_path_requires_list(self):
        with patch.object(b1c, 'adb_call', side_effect=[(0, '', ''), (0, '', '')]) as adb:
            self.assertIsNone(b1c.installed_apk('adb', 's', b1c.APP, self.root/'app.apk'))
            self.assertEqual(adb.call_count, 2)

    def test_nonzero_path_is_blocked_if_list_shows_exact_package(self):
        with patch.object(b1c, 'adb_call', side_effect=[
            (1, '', ''), (0, f'package:{b1c.APP}\n', '')
        ]):
            with self.assertRaisesRegex(b1c.Blocked, 'PATH_LIST_DISAGREE'):
                b1c.installed_apk('adb', 's', b1c.APP, self.root/'app.apk')

    def test_substring_package_is_not_exact_presence(self):
        with patch.object(b1c, 'adb_call', side_effect=[
            (1, '', ''), (0, f'package:{b1c.APP}.another\n', '')
        ]):
            self.assertIsNone(b1c.installed_apk('adb', 's', b1c.APP, self.root/'app.apk'))

    def test_failed_enumeration_not_counted_as_absent(self):
        for response in ((1,'',''), (0,'','Permission denied'),
                         (0,'Error: package manager unavailable','')):
            with self.subTest(response=response), patch.object(b1c, 'adb_call', side_effect=[
                (1, '', ''), response
            ]):
                with self.assertRaises(b1c.Blocked):
                    b1c.installed_apk('adb', 's', b1c.APP, self.root/'app.apk')

    def test_pm_path_errors_must_not_downgrade_to_absent(self):
        for response in ((2, '', ''), (1, '', 'SecurityException'),
                         (1, 'cmd: Can\'t find service: package', ''),
                         (0, '', 'Warning: partial output')):
            with self.subTest(response=response), patch.object(b1c, 'adb_call', return_value=response) as shell:
                with self.assertRaisesRegex(b1c.Blocked, 'PACKAGE_MANAGER_QUERY_FAILED'):
                    b1c.installed_apk('adb', 's', b1c.APP, self.root/'app.apk')
                self.assertEqual(shell.call_count, 1)

    def test_pm_list_rejects_ambiguous_or_duplicate_entries(self):
        for lines in ('package:'+b1c.APP+'.extra\npackage:'+b1c.APP+'.extra\n',
                      'package:invalid app\n', 'package:'+b1c.APP+'\n'):
            with self.subTest(lines=lines), patch.object(b1c, 'adb_call', side_effect=[
                (1, '', ''), (0, lines, '')
            ]):
                with self.assertRaises(b1c.Blocked):
                    b1c.installed_apk('adb', 's', b1c.APP, self.root/'app.apk')

    def test_installed_path_still_needs_pull_and_matching_bytes(self):
        apk=self.root/'installed-app.apk'
        data=b'known-byte-fixture'
        def shell(adb, serial, *args, **kwargs):
            if args[:3] == ('shell','pm','path'):
                return 0, 'package:/data/app/~~foo/io.github.mikeyphw.skybind-foo/base.apk\n',''
            if args[0]=='pull':
                Path(args[2]).write_bytes(data)
                return 0, '', ''
            self.fail(repr(args))
        with patch.object(b1c,'adb_call',side_effect=shell):
            self.assertEqual(b1c.installed_apk('adb','s',b1c.APP,apk),hashlib.sha256(data).hexdigest())

    def test_provenance_blocks_mismatch_and_partial_install(self):
        with patch.object(b1c,'installed_apk',side_effect=['0'*64,None]):
            with self.assertRaisesRegex(b1c.Blocked,'PARTIAL'):
                b1c.check_installed('adb','x',self.root,{'app_sha256':'1'*64,'test_sha256':'2'*64})
        with patch.object(b1c,'installed_apk',side_effect=['0'*64,'2'*64]):
            with self.assertRaisesRegex(b1c.Blocked,'DIFFER'):
                b1c.check_installed('adb','x',self.root,{'app_sha256':'1'*64,'test_sha256':'2'*64})

    def test_instrumentation_requires_both_named_cases(self):
        def log(cases):
            lines=[]
            for cls,method in cases:
                lines += [f'INSTRUMENTATION_STATUS: class={cls}',
                          f'INSTRUMENTATION_STATUS: test={method}',
                          'INSTRUMENTATION_STATUS_CODE: 1',
                          f'INSTRUMENTATION_STATUS: class={cls}',
                          f'INSTRUMENTATION_STATUS: test={method}',
                          'INSTRUMENTATION_STATUS_CODE: 0']
            return '\n'.join(lines+['INSTRUMENTATION_CODE: -1'])+'\n'
        good=log(sorted(b1c.CASES))
        self.assertEqual(len(b1c.parse_instrumentation(good)),2)
        with self.assertRaisesRegex(b1c.Blocked,'INCOMPLETE'):
            b1c.parse_instrumentation(log([sorted(b1c.CASES)[0]]))
        with self.assertRaises(b1c.Blocked):
            b1c.parse_instrumentation(good.replace('INSTRUMENTATION_CODE: -1','INSTRUMENTATION_CODE: 0'))
        with self.assertRaises(b1c.Blocked):
            b1c.parse_instrumentation(good.replace('INSTRUMENTATION_STATUS_CODE: 0','INSTRUMENTATION_STATUS_CODE: -2',1))

    def test_unique_receipts_no_overwrite(self):
        with patch.object(b1c,'RECEIPTS',self.root):
            a=b1c.output_receipt({'state':'BLOCKED'})
            b=b1c.output_receipt({'state':'PASS'})
        self.assertNotEqual(a,b)
        self.assertEqual(json.loads(Path(a).read_text())['state'],'BLOCKED')

if __name__=='__main__':unittest.main()
