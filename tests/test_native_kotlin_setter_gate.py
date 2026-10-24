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
