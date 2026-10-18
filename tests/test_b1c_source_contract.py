"""Source policy to preserve hosted build and B1-C device isolation."""
from pathlib import Path
import tomllib
import unittest

ROOT=Path(__file__).resolve().parents[1]

class Contract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc=tomllib.loads((ROOT/'.devtool.toml').read_text())
        cls.script=(ROOT/'scripts/dev/android/r1_b1c_device.py').read_text()

    def test_device_jobs_are_exclusive_and_evidence_writers(self):
        jobs=self.doc['targets']['skybind_android_device']['jobs']
        for key in ('b1c-hosted-provenance','b1c-hosted-instrumentation'):
            job=jobs[key]
            self.assertIs(job['metadata']['read_only'],False)
            self.assertIn('skybind:physical-device',job['metadata']['global_reservations'])
            self.assertIs(job['metadata']['production_broker_enabled'],False)
            self.assertIn('build/evidence/android/b1c',str(job['outputs']))

    def test_wrapper_contract(self):
        w=self.doc['wrapper']['commands']
        self.assertEqual(w['r1-device-provenance']['workflow'],'b1c-hosted-provenance')
        self.assertEqual(w['r1-device-instrumentation']['workflow'],'b1c-hosted-instrumentation')

    def test_no_implicit_mutations(self):
        self.assertNotIn("'uninstall'",self.script.split('def install_missing')[1].split('def parse_instrumentation')[0])
        self.assertNotIn("'install','-r'",self.script)
        self.assertIn("args.mode=='instrument' and args.install_missing",self.script)
        self.assertIn('INSTALLED_APK_BYTES_DIFFER_FROM_HOSTED_EVIDENCE',self.script)
        self.assertIn('PASS_B1C_DEVICE_INSTRUMENTATION',self.script)

    def test_hosted_provenance_is_exact(self):
        self.assertIn('be9ee025156643fe9a5c21d577dd0d2f',self.script)
        self.assertIn('1b808119720ed3c042ffc2a8fa84ebe313697eb8',self.script)
        self.assertEqual(self.doc['targets']['skybind_android_app']['root'],'android-app')
        self.assertNotIn('r1-device-instrumentation',str(self.doc['targets']['skybind_release'].get('workflows',{})))

if __name__=='__main__':unittest.main()
