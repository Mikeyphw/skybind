"""Source-only checks: no Android build, no device mutation."""
import pathlib
import tomllib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
class R1BConfig(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=tomllib.loads((ROOT/'.devtool.toml').read_text())
    def test_source_dag_retains_all_authorities(self):
        targets=self.config['targets']
        assert {'r1-identity-source','r1-full-regression'} <= targets['skybind_release']['workflows'].keys()
        rows=targets['skybind_release']['workflows']['r1-identity-source']
        self.assertEqual({x['id'] for x in rows},{'transport','identity','source-policy'})
        self.assertIn('r1-transport-source',rows[0]['ref'])
        self.assertIn('r1-identity',rows[1]['ref'])
        self.assertIn('r1-identity-source',targets['skybind_release']['workflows']['r1-full-regression'][0]['ref'])
    def test_no_android_local_build(self):
        job=self.config['targets']['skybind_api_contracts']['jobs']['r1-identity']
        self.assertEqual(job['command'][:3], ['go','test','-count=1'])
        self.assertFalse(job['metadata']['production_listener_enabled'])
        self.assertFalse(job['metadata']['android_package_attestor_live'])
        appjob=self.config['targets']['skybind_android_app']['jobs']['build-policy']
        self.assertNotIn('gradle',' '.join(appjob['command']).lower())
    def test_package_manager_not_a_trust_channel(self):
        src=(ROOT/'android-app/app/src/main/java/io/github/mikeyphw/skybind/security/UidPackageEvidence.kt').read_text()
        self.assertIn('hasSigningCertificate',src)
        self.assertIn('packages.size != 1',src)
        self.assertNotIn('Runtime.getRuntime()',src)

if __name__=='__main__':unittest.main()
