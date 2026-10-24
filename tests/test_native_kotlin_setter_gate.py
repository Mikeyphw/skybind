# Regression for GitHub personal APK run 40046033979 Kotlin setter collisions.
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / 'scripts/dev/android/native_kotlin_setter_gate.py'
spec = importlib.util.spec_from_file_location('native_kotlin_setter_gate', GATE)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

class NativeKotlinSetterGateTests(unittest.TestCase):
    def test_real_tree_has_no_colliding_jvm_accessors(self):
        self.assertEqual(gate.verify(ROOT)['status'], 'PASS_NATIVE_KOTLIN_SETTER_SOURCE_GUARD_ONLY')

    def test_current_android_test_source_imports_are_legal(self):
        details = gate.verify(ROOT)
        self.assertGreater(details['android_test_files_checked'], 5)
        self.assertFalse(details['android_test_compiled'])

    def test_reject_both_invalid_android_test_compose_imports(self):
        raw = ('import androidx.compose.ui.test.assertExists\n'
               'import androidx.compose.ui.test.assertDoesNotExist\n')
        self.assertEqual(gate.invalid_androidtest_imports(raw),
                         ['assertExists', 'assertDoesNotExist'])

    def test_semantics_node_interaction_member_calls_still_accepted(self):
        raw = ('import androidx.compose.ui.test.onNodeWithTag\n'
               'fun check() { compose.onNodeWithTag("x").assertExists()\n'
               '  compose.onNodeWithTag("y").assertDoesNotExist() }')
        self.assertEqual(gate.invalid_androidtest_imports(raw), [])

    def test_android_test_import_failure_reproduced_from_run_40051717952(self):
        from tempfile import TemporaryDirectory
        import shutil
        with TemporaryDirectory() as temp:
            dest = Path(temp) / 'repo'
            shutil.copytree(ROOT / 'android-app', dest / 'android-app')
            shutil.copytree(ROOT / 'scripts', dest / 'scripts')
            # Only verify the original fault at the source level. Do not impersonate Gradle.
            bad = dest / 'android-app/app/src/androidTest/java/io/github/mikeyphw/skybind/NativePersonalLiveTest.kt'
            bad.write_text(bad.read_text().replace(
                'import androidx.compose.ui.test.onNodeWithTag',
                'import androidx.compose.ui.test.assertExists\nimport androidx.compose.ui.test.onNodeWithTag'))
            self.assertEqual(gate.invalid_androidtest_imports(bad.read_text()), ['assertExists'])

    def test_mainactivity_old_collision_rejected(self):
        self.assertEqual(gate.find_collisions('''class MainActivity {
            private var bkxKeepBackground by mutableStateOf(true)
            private fun setBkxKeepBackground(keep: Boolean) { }
        }'''), ['setBkxKeepBackground'])

    def test_viewmodel_old_collision_rejected(self):
        self.assertEqual(gate.find_collisions('''class SessionViewModel {
            var autoConnectEnabled by mutableStateOf(true)
                private set
            fun setAutoConnectEnabled(enabled: Boolean) { }
        }'''), ['setAutoConnectEnabled'])

    def test_safe_preference_handlers_accepted(self):
        self.assertEqual(gate.find_collisions('''class MainActivity {
            private var bkxKeepBackground by mutableStateOf(true)
            private fun updateBkxBackgroundPreference(keep: Boolean) { }
        }'''), [])

    def test_explicit_getter_collision_rejected(self):
        self.assertEqual(gate.find_collisions('''class Example {
            private var mountHealth = 0
            fun getMountHealth(): Int = 0
        }'''), ['getMountHealth'])

    def test_multiple_conflicts_rejected(self):
        self.assertEqual(gate.find_collisions('''class Example {
            var enabled = false
            fun getEnabled() = false
            fun setEnabled(value: Boolean) { }
        }'''), ['getEnabled', 'setEnabled'])

if __name__ == '__main__': unittest.main()
