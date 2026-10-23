"""Failure-oriented source contracts for Skybind's native M1 UI."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / 'scripts/dev/android/m1_native_source_gate.py'
spec = importlib.util.spec_from_file_location('m1_native_source_gate', P)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class NativeM1SourceTests(unittest.TestCase):
    def test_real_source_contract(self):
        self.assertEqual(mod.verify(ROOT)['state'], 'PASS_M1_FOREGROUND_AUTO_BRIDGE_SOURCE_ONLY')

    def copy_fixture(self, files):
        d = tempfile.TemporaryDirectory()
        base = Path(d.name)
        required = [
            mod.MAIN / 'MainActivity.kt', mod.MAIN / 'model/SkybindReadModel.kt',
            mod.MAIN / 'ui/SkybindApp.kt', mod.TEST / 'NativeUiTest.kt', mod.TEST / 'NativeLifecycleTest.kt',
            Path('android-app/app/src/main/AndroidManifest.xml'),
            Path('android-app/app/build.gradle.kts'), Path('android-app/settings.gradle.kts'),
            Path('android-app/app/src/main/aidl/io/github/mikeyphw/skybind/bridge/IRootReadBridge.aidl'),
            mod.MAIN / 'bridge/RootReadBridgeService.kt',
            mod.MAIN / 'bridge/RootReadSession.kt',
            mod.MAIN / 'bridge/SkybindSessionViewModel.kt',
            mod.MAIN / 'bridge/LiveReadSnapshotReader.kt',
            mod.TEST / 'LiveReadGatewayTest.kt',
            Path('.github/workflows/skybind-android-apks.yml'),
        ]
        for p in required:
            target = base / p
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT/p, target)
        for path, old, new in files:
            f = base / path
            value = f.read_text()
            self.assertIn(old, value)
            f.write_text(value.replace(old, new, 1))
        return d, base

    def rejects(self, path, old, new):
        temporary, root = self.copy_fixture([(path, old, new)])
        with temporary:
            with self.assertRaises(mod.Violation):
                mod.verify(root)

    def test_missing_default_deny_is_rejected(self):
        self.rejects(mod.MAIN / 'MainActivity.kt', 'SkybindSessionViewModel by viewModels()', 'PermissiveViewModel by viewModels()')

    def test_permission_escalation_is_rejected(self):
        self.rejects(Path('android-app/app/src/main/AndroidManifest.xml'), '<application', '<uses-permission android:name="android.permission.INTERNET"/><application')

    def test_job_history_conflation_is_rejected(self):
        self.rejects(mod.MAIN / 'model/SkybindReadModel.kt', 'events.distinctBy', 'jobs.distinctBy')

    def test_missing_device_tests_rejected(self):
        self.rejects(mod.TEST / 'NativeUiTest.kt', 'fun unpairedStateHidesStaleServerData', 'fun removedDeviceTest')

    def test_missing_activity_recreation_is_rejected(self):
        self.rejects(mod.TEST / 'NativeLifecycleTest.kt', 'scenario.recreate()', 'fakeRecreate()')

    def test_privileged_exec_is_rejected(self):
        self.rejects(mod.MAIN / 'MainActivity.kt', 'setContent {', 'Runtime.getRuntime(\"su\"); setContent {')

if __name__ == '__main__':
    unittest.main()
