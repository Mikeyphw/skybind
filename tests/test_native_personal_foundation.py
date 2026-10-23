"""Negative cases for the NATIVE-00/01 Android source contract."""
from pathlib import Path
import importlib.util
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
P = ROOT/'scripts/dev/android/native_personal_foundation_gate.py'
spec = importlib.util.spec_from_file_location('native_foundation_gate',P)
gate = importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)

class FoundationSourceContract(unittest.TestCase):
    def test_real_tree(self):
        self.assertEqual(gate.verify(ROOT)['state'],'PASS_NATIVE_FOUNDATION_SOURCE_ONLY')

    def denied(self, rel, needle, substitution):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)
            files=[gate.MAIN/'MainActivity.kt',gate.MAIN/'ui/SkybindApp.kt',
                gate.MAIN/'bridge/SkybindSessionViewModel.kt',
                gate.MAIN/'bridge/RootReadSession.kt',
                gate.MAIN/'bridge/RootReadBridgeService.kt',
                gate.MAIN/'bridge/LiveReadSnapshotReader.kt',
                Path('android-app/app/src/main/AndroidManifest.xml'),
                Path('android-app/app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml')]
            files+=list(Path('android-app/app/src/main/res/drawable')/name
                        for name in ('ic_launcher_foreground.xml','ic_launcher_monochrome.xml','ic_launcher_background.xml'))
            for file in files:
                dst=base/file;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/file,dst)
            src=base/rel
            self.assertIn(needle,src.read_text())
            src.write_text(src.read_text().replace(needle,substitution,1))
            with self.assertRaises(gate.Violation):gate.verify(base)

    def test_mount_status_forgery_rejected(self):
        self.denied(gate.MAIN/'bridge/LiveReadSnapshotReader.kt',
                    'value.optString("name") != name', 'false')

    def test_auto_root_missing_rejected(self):
        self.denied(gate.MAIN/'MainActivity.kt','session.onForeground()', 'session.refresh()')

    def test_root_query_must_remain_query(self):
        self.denied(gate.MAIN/'bridge/RootReadBridgeService.kt',
                    'rpc(method, "query", checkedReadArguments(method, arguments))',
                    'rpc(method, "run", checkedReadArguments(method, arguments))')

    def test_icon_missing_rejected(self):
        self.denied(Path('android-app/app/src/main/AndroidManifest.xml'),
                    'android:icon="@mipmap/ic_launcher"', 'android:icon="@drawable/not-present"')

if __name__=='__main__':unittest.main()
