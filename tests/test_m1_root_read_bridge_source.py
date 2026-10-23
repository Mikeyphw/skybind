"""Fail-closed source checks for the explicit-only RootService transport."""
from pathlib import Path
import importlib.util
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / 'scripts/dev/android/m1_native_source_gate.py'
spec = importlib.util.spec_from_file_location('m1_source_contract', source)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

class RootReadBridgeContract(unittest.TestCase):
    def test_complete_source_contract(self):
        self.assertEqual(gate.verify(ROOT)['read_only_gateway'], 'ROOT_SERVICE_FOREGROUND_AUTO_APPROVAL')

    def run_negative(self, rel, before, after):
        with tempfile.TemporaryDirectory(prefix='skybind-m1-negative-') as name:
            folder = Path(name)
            for path in [
                gate.MAIN/'MainActivity.kt', gate.MAIN/'model/SkybindReadModel.kt',
                gate.MAIN/'ui/SkybindApp.kt', gate.MAIN/'bridge/RootReadBridgeService.kt',
                gate.MAIN/'bridge/RootReadSession.kt', gate.MAIN/'bridge/SkybindSessionViewModel.kt',
                gate.MAIN/'bridge/LiveReadSnapshotReader.kt',
                gate.TEST/'NativeUiTest.kt', gate.TEST/'NativeLifecycleTest.kt', gate.TEST/'LiveReadGatewayTest.kt',
                Path('android-app/app/src/main/aidl/io/github/mikeyphw/skybind/bridge/IRootReadBridge.aidl'),
                Path('android-app/app/src/main/AndroidManifest.xml'), Path('android-app/settings.gradle.kts'),
                Path('android-app/app/build.gradle.kts'), Path('.github/workflows/skybind-android-apks.yml')]:
                dst=folder/path;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/path,dst)
            target=folder/rel;body=target.read_text();self.assertIn(before,body)
            target.write_text(body.replace(before,after,1))
            with self.assertRaises(gate.Violation):gate.verify(folder)

    def test_cannot_skip_caller_uid(self):
        self.run_negative(gate.MAIN/'bridge/RootReadBridgeService.kt',
            'Binder.getCallingUid()', 'Process.myUid()')

    def test_cannot_add_mutating_rpc(self):
        self.run_negative(gate.MAIN/'bridge/RootReadBridgeService.kt',
            '"operation.events"', '"config.apply"')

    def test_cannot_remove_canonical_socket_identity(self):
        self.run_negative(gate.MAIN/'bridge/RootReadBridgeService.kt',
            'socket.peerCredentials.uid != 0', 'false')

    def test_cannot_remove_auto_root_wiring(self):
        self.run_negative(gate.MAIN/'MainActivity.kt',
            'onConnect = session::connect', 'onConnect = session::refresh')

    def test_cannot_remove_event_gap_detection(self):
        self.run_negative(gate.MAIN/'bridge/LiveReadSnapshotReader.kt',
            'cursor_reset', 'not_cursor_reset')

    def test_cannot_drop_rpc_query_only_class(self):
        self.run_negative(gate.MAIN/'bridge/RootReadBridgeService.kt',
            'rpc(method, "query", checkedReadArguments(method, arguments))',
            'rpc(method, "run", checkedReadArguments(method, arguments))')

if __name__ == '__main__': unittest.main()
