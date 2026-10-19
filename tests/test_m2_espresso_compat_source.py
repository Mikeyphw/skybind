"""Negative source regressions for Compose UI's transitive Espresso linkage."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
S = ROOT / 'scripts/dev/android/m2_espresso_source_gate.py'
spec = importlib.util.spec_from_file_location('m2_espresso_source_gate', S)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class EspressoCompatibilitySourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gradle = (ROOT / module.MODULE).read_text()
        cls.required = 'androidTestImplementation("androidx.test.espresso:espresso-core:3.7.0")'

    def rejects(self, code):
        with self.assertRaises(module.Violation):
            module.check_gradle(code)

    def test_current_explicit_dependency(self):
        self.assertEqual(module.verify(ROOT)['state'], 'PASS_M2_ESPRESSO_ANDROID36_SOURCE_COMPAT')

    def test_absent_dependency_fails_closed(self):
        self.rejects(self.gradle.replace(self.required, '', 1))

    def test_transitive_legacy_version_fails_closed(self):
        self.rejects(self.gradle.replace(self.required, self.required.replace('3.7.0','3.5.0'), 1))

    def test_previous_3_6_1_version_fails_closed(self):
        self.rejects(self.gradle.replace(self.required, self.required.replace('3.7.0','3.6.1'), 1))

    def test_commented_out_pin_fails_closed(self):
        self.rejects(self.gradle.replace(self.required, '// '+self.required, 1))

    def test_duplicate_version_fails_closed(self):
        self.rejects(self.gradle.replace(self.required, self.required+'\n    '+self.required, 1))

    def test_loss_of_compose_ui_testing_fails_closed(self):
        self.rejects(self.gradle.replace(module.COMPOSE, '', 1))

    def test_strict_source_file_not_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = root / module.MODULE
            p.parent.mkdir(parents=True)
            p.symlink_to(ROOT / module.MODULE)
            with self.assertRaises(module.Violation):
                module.verify(root)


if __name__ == '__main__':
    unittest.main()
