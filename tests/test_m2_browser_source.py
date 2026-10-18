"""M2 source-gate negative tests: preserve a narrow read-only privilege surface."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
filename = ROOT / 'scripts/dev/android/m2_browser_source_gate.py'
spec = importlib.util.spec_from_file_location('m2_native', filename)
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)

class BrowserSafetyRegression(unittest.TestCase):
    def test_source_contract(self):
        self.assertEqual(check.verify(ROOT)['state'], 'PASS_M2_REMOTE_BROWSER_SOURCE_ONLY')

    def negative(self, rel, before, after):
        with tempfile.TemporaryDirectory(prefix='skybind-m2-regress-') as tmp:
            dest = Path(tmp)
            files = [
                'bridge/RootReadBridgeService.kt', 'bridge/RemoteBrowseReader.kt',
                'model/RemoteBrowseModel.kt', 'bridge/RootReadSession.kt',
                'bridge/SkybindSessionViewModel.kt', 'MainActivity.kt', 'ui/SkybindApp.kt',
            ]
            for part in files:
                relative = check.MAIN / part
                out = dest / relative
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT/relative, out)
            other = check.TEST
            out = dest/other
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT/other, out)
            path = dest / rel
            body = path.read_text()
            self.assertIn(before, body)
            path.write_text(body.replace(before, after, 1))
            with self.assertRaises(check.Violation):
                check.verify(dest)

    def test_reject_browse_as_a_mutation(self):
        self.negative(check.MAIN/'bridge/RootReadBridgeService.kt',
                      '"class", "query"', '"class", "run"')

    def test_reject_missing_root_socket_peer_check(self):
        self.negative(check.MAIN/'bridge/RootReadBridgeService.kt',
                      'socket.peerCredentials.uid != 0', 'false')

    def test_reject_unbounded_folder_listing(self):
        self.negative(check.MAIN/'bridge/RemoteBrowseReader.kt',
                      'data.length() <= 500', 'data.length() <= 50000')

    def test_reject_out_of_folder_entries(self):
        self.negative(check.MAIN/'bridge/RemoteBrowseReader.kt',
                      'require(reported == name || reported == childPath)', 'require(true)')

    def test_reject_dropped_stale_generation(self):
        self.negative(check.MAIN/'bridge/SkybindSessionViewModel.kt',
                      'token == browseGeneration && snapshot.online', 'snapshot.online')

    def test_reject_browse_disconnected_leak(self):
        self.negative(check.MAIN/'model/RemoteBrowseModel.kt',
                      '!snapshot.online', 'false')

    def test_reject_missing_disabled_write_action(self):
        self.negative(check.MAIN/'ui/SkybindApp.kt',
                      '"browser-write-disabled"', '"browser-write-enabled"')

if __name__ == '__main__':
    unittest.main()
