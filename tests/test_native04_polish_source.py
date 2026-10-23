"""NATIVE-04 positive and fail-closed source tests; no APK claims."""
from pathlib import Path
import importlib.util
import tempfile
import shutil
import unittest
ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'scripts/dev/android/native04_polish_gate.py'
spec=importlib.util.spec_from_file_location('native04_gate',PATH)
gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
class NativePolishSource(unittest.TestCase):
    def test_real_source(self):
        self.assertEqual(gate.verify(ROOT)['state'],'PASS_NATIVE_04_POLISH_SOURCE_ONLY')
    def check_removed(self, rel, needle):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)
            paths=[gate.BASE/'model/SkybindReadModel.kt',gate.BASE/'ui/SkybindApp.kt',
                gate.BASE/'ui/NativePresentation.kt',gate.BASE/'bridge/LiveReadSnapshotReader.kt',
                gate.BASE/'bridge/RootReadBridgeService.kt',gate.BASE/'MainActivity.kt',
                gate.BASE/'bridge/R1PMBridgeAgent.kt',gate.BASE/'bridge/R1AuthorityService.kt',
                Path('android-app/app/src/main/AndroidManifest.xml'),
                Path('android-app/app/src/androidTest/java/io/github/mikeyphw/skybind/NativePolishUiTest.kt'),
                Path('android-app/app/src/androidTest/java/io/github/mikeyphw/skybind/LiveReadGatewayTest.kt')]
            for path in paths:
                dest=base/path;dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT/path,dest)
            target=base/rel
            self.assertIn(needle,target.read_text())
            target.write_text(target.read_text().replace(needle,'',1))
            with self.assertRaises(gate.Violation):gate.verify(base)
    def test_fake_runtime_status_fails(self):
        self.check_removed(gate.BASE/'bridge/LiveReadSnapshotReader.kt','runtime.opt("ready") !is Boolean')
    def test_mount_health_identity_rejected(self):
        self.check_removed(gate.BASE/'bridge/LiveReadSnapshotReader.kt','health.optString("name") != name')
    def test_query_to_run_escalation_rejected(self):
        self.check_removed(gate.BASE/'bridge/RootReadBridgeService.kt',
                           'rpc(method, "query", checkedReadArguments(method, arguments))')
    def test_bkx_optin_rejected_when_removed(self):
        self.check_removed(gate.BASE/'MainActivity.kt','onEnableBkx = ::enableAuthority')
    def test_lazy_journal_rejected_when_removed(self):
        self.check_removed(gate.BASE/'ui/SkybindApp.kt','items(filtered, key = { it.sequence })')
    def test_build_signer_provenance_rejected(self):
        self.check_removed(gate.BASE/'ui/NativePresentation.kt','MessageDigest.getInstance("SHA-256")')
if __name__=='__main__':unittest.main()
