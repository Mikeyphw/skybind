"""Negative source checks; no substitute for Android instrumentation."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('native_config',ROOT/'scripts/dev/android/native_mount_config_gate.py')
gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
FILES=[gate.AIDL,gate.MAIN/'bridge/RootReadBridgeService.kt',gate.MAIN/'bridge/RootReadSession.kt',
       gate.MAIN/'bridge/SkybindSessionViewModel.kt',gate.MAIN/'ui/SkybindApp.kt',
       gate.MAIN/'ui/MountConfigEditor.kt',gate.MAIN/'model/MountConfigModel.kt',gate.MAIN/'MainActivity.kt']
class NativeMountConfigContract(unittest.TestCase):
    def test_complete_source(self):
        self.assertEqual(gate.verify(ROOT)['state'],'PASS_NATIVE_03_CONFIG_SOURCE_SECURITY_ONLY')
    def reject(self,file,before,after):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for name in FILES:
                dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,dest)
            target=root/file
            raw=target.read_text();self.assertIn(before,raw)
            target.write_text(raw.replace(before,after,1))
            with self.assertRaises(gate.Violation):gate.verify(root)
    def test_session_binding(self):self.reject(gate.MAIN/'bridge/RootReadBridgeService.kt',
        'config preview already consumed")\n            if (ticket.session != session',
        'config preview already consumed")\n            if (false')
    def test_single_use(self):self.reject(gate.MAIN/'bridge/RootReadBridgeService.kt',
        'val ticket = synchronized(gate) { configTickets.remove(previewId) }',
        'val ticket = synchronized(gate) { configTickets[previewId] }')
    def test_revision_conflict(self):self.reject(gate.MAIN/'bridge/RootReadBridgeService.kt',
        'checkedRegistry().getLong("revision") != ticket.revision', 'false')
    def test_exact_binder_surface(self):self.reject(gate.AIDL,'String previewDeleteMount(', 'String patch(')
    def test_proof_stays_in_root(self):self.reject(gate.MAIN/'bridge/RootReadBridgeService.kt',
        '// App gets only a scoped ticket and a human-readable diff, never the daemon proof.',
        '// App gets only a scoped ticket and a human-readable diff, never the daemon proof.\n            JSONObject().put("proof", proof)')
    def test_query_not_mutation(self):self.reject(gate.MAIN/'bridge/RootReadBridgeService.kt',
        'rpc(method, "query", checkedReadArguments(method, arguments))',
        'rpc(method, "run", checkedReadArguments(method, arguments))')
    def test_ui_requires_checkbox(self):self.reject(gate.MAIN/'ui/MountConfigEditor.kt',
        'enabled = !busy && consent', 'enabled = !busy')
    def test_no_unreviewed_config_rpc(self):self.reject(gate.MAIN/'bridge/RootReadBridgeService.kt',
        '"config.apply", "run"', '"config.rollback", "run"')
    def test_rollback_consumes_ticket(self):self.reject(gate.MAIN/'bridge/RootReadBridgeService.kt',
        'val ticket = synchronized(gate) { rollbackTickets.remove(previewId) }',
        'val ticket = synchronized(gate) { rollbackTickets[previewId] }')
    def test_rollback_requires_session(self):self.reject(gate.MAIN/'bridge/RootReadBridgeService.kt',
        'if (ticket.session != session || ticket.deadline <= SystemClock.elapsedRealtime())\n                throw SecurityException("foreign or expired rollback ticket")',
        'if (false)\n                throw SecurityException("foreign or expired rollback ticket")')
    def test_rollback_requires_revision(self):self.reject(gate.MAIN/'bridge/RootReadBridgeService.kt',
        'if (checkedRegistry().getLong("revision") != ticket.revision)\n                throw SecurityException("registry changed since rollback preview")',
        'if (false)\n                throw SecurityException("registry changed since rollback preview")')
    def test_rollback_requires_consent(self):self.reject(gate.MAIN/'ui/SkybindApp.kt',
        'enabled = approved && !rollbackBusy', 'enabled = !rollbackBusy')
    def test_daemon_field_errors_bound_to_edited_mount(self):self.reject(gate.MAIN/'bridge/RootReadBridgeService.kt',
        'item?.optInt("index", -1) == candidate.length() - 1',
        'item != null')
    def test_no_implicit_root_config(self):self.reject(gate.MAIN/'bridge/SkybindSessionViewModel.kt',
        'private fun connectInternal() {', 'private fun connectInternal() {\n        bridge.applyConfig(preview)')
if __name__=='__main__':unittest.main()
