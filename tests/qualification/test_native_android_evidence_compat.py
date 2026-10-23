"""NATIVE-00: a changed Android app must NEVER inherit old APK evidence."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/dev/qualification/personal_policy.py'
spec = importlib.util.spec_from_file_location('native_personal_policy', SCRIPT)
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)

class AndroidEvidenceSourceCompatibility(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='skybind-native-lineage-')
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.git('init', '-q')
        self.git('config', 'user.email', 'skybind-test@example.invalid')
        self.git('config', 'user.name', 'Skybind test')
        self.write('docs/baseline.md', 'baseline')
        self.git('add', '.')
        self.git('commit', '-qm', 'baseline')
        self.base = self.git('rev-parse', 'HEAD')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], text=True).strip()

    def write(self, path, content):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)

    def compatible(self, path):
        self.write(path, 'updated')
        self.git('add', '.')
        self.git('commit', '-qm', 'delta')
        head = self.git('rev-parse', 'HEAD')
        docs = {'q16': {'run': {'commit': self.base}},
                'q17': {'source_commit': self.base},
                'm2m3': {'source_sha': self.base}}
        return policy.product_compatible(self.repo, {'commit': head}, docs)

    def test_documentation_is_safe(self):
        self.assertTrue(self.compatible('docs/qualification/new.md'))

    def test_reviewed_local_build_tooling_only_is_safe(self):
        self.assertTrue(self.compatible('scripts/dev/integration/local_build.py'))

    def test_contract_catalog_rejects_stale_receipt(self):
        self.assertFalse(self.compatible("docs/contracts/typed-operations.json"))

    def test_android_kotlin_rejects_stale_receipt(self):
        self.assertFalse(self.compatible('android-app/app/src/main/java/Example.kt'))

    def test_aidl_rejects_stale_receipt(self):
        self.assertFalse(self.compatible('android-app/app/src/main/aidl/IControl.aidl'))

    def test_branding_icon_rejects_stale_receipt(self):
        self.assertFalse(self.compatible('android-app/app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml'))

    def test_android_ci_workflow_rejects_stale_receipt(self):
        self.assertFalse(self.compatible('.github/workflows/skybind-android-apks.yml'))

    def test_unknown_root_path_rejects_stale_receipt(self):
        self.assertFalse(self.compatible('new-product-surface.txt'))

    def test_android_test_harness_is_conservative(self):
        self.assertFalse(self.compatible('scripts/dev/android/m2_m3_retest_batch.py'))

    def test_source_equal_to_receipt_is_compatible(self):
        docs = {'q16': {'run': {'commit': self.base}},
                'q17': {'source_commit': self.base},
                'm2m3': {'source_sha': self.base}}
        self.assertTrue(policy.product_compatible(self.repo, {'commit': self.base}, docs))

    def test_cross_source_receipts_not_compatible(self):
        docs = {'q16': {'run': {'commit': self.base}},
                'q17': {'source_commit': 'd'*40},
                'm2m3': {'source_sha': self.base}}
        self.assertFalse(policy.product_compatible(self.repo, {'commit': self.base}, docs))

if __name__ == '__main__': unittest.main()
