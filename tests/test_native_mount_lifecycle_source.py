import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
R=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('lifecycle_gate',R/'scripts/dev/android/native_mount_lifecycle_gate.py')
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
FILES=[g.AIDL, g.JAVA/'bridge/RootReadBridgeService.kt',g.JAVA/'bridge/RootReadSession.kt',
       g.JAVA/'bridge/SkybindSessionViewModel.kt',g.JAVA/'ui/SkybindApp.kt',g.JAVA/'MainActivity.kt']
class LifecycleSourceTests(unittest.TestCase):
    def test_tree(self): self.assertEqual(g.verify(R)['state'],'PASS_NATIVE_02_STATIC_GUARD_ONLY')
    def reject(self,rel,a,b):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for f in FILES:
                dest=root/f;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(R/f,dest)
            body=(root/rel).read_text();self.assertIn(a,body)
            (root/rel).write_text(body.replace(a,b,1))
            with self.assertRaises(g.Violation):g.verify(root)
    def test_no_reused_ticket(self):self.reject(g.JAVA/'bridge/RootReadBridgeService.kt',
        'mountTickets.remove(previewId)','mountTickets[previewId]')
    def test_no_foreign_session(self):self.reject(g.JAVA/'bridge/RootReadBridgeService.kt',
        'mountTicket.session != session','false')
    def test_no_stale_revision(self):self.reject(g.JAVA/'bridge/RootReadBridgeService.kt',
        'registry.optLong("revision", -1) != mountTicket.revision','false')
    def test_no_unauthorized_rpc(self):self.reject(g.JAVA/'bridge/RootReadBridgeService.kt',
        '"mount.stop"','"config.apply"')
    def test_no_lost_binder_identity(self):self.reject(g.JAVA/'bridge/RootReadSession.kt',
        'fun confirmMount(', 'fun confirmArbitrary(')
    def test_no_ui_bypass(self):self.reject(g.JAVA/'ui/SkybindApp.kt',
        'enabled = !mountBusy && acknowledged','enabled = !mountBusy')
    def test_no_removed_disconnect_clear(self):self.reject(g.JAVA/'bridge/SkybindSessionViewModel.kt',
        'mountOperation?.cancel()', '/* omitted */')
if __name__=='__main__':unittest.main()
