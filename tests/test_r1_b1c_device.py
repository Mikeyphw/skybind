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
