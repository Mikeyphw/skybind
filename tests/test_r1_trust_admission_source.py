"""Fail closed if source claims external R1 delivery before authenticated linkage."""
from __future__ import annotations
import importlib.util
import pathlib
import shutil
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('r1_gate', ROOT/'scripts/dev/android/r1_trust_admission_source_gate.py')
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class AdmissionGate(unittest.TestCase):
    def test_actual_source_default_denied(self):
        r = module.evaluate(ROOT)
        self.assertEqual(r['status'], 'PASS_R1_ADMISSION_SOURCE_DEFAULT_DENY', r)
        self.assertFalse(r['live_external_transport_activated'])
        self.assertFalse(r['release_qualified'])

    def test_unknown_abi_claim_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = pathlib.Path(directory)
            (temp/'docs/contracts/rclone-compat').mkdir(parents=True)
            for name in module.REQUIRED:
                src = ROOT/name; dst = temp/name
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            for name in ('cmd/skybind/main.go', 'module/service.sh'):
                dst = temp/name; dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT/name, dst)
            abi = temp/'docs/contracts/rclone-compat/SKYBIND_CONSUMER_ABI_V1.json'
            abi.write_text(abi.read_text().replace('"available_external_capabilities": []', '"available_external_capabilities": ["rclone.restic-stdio.v1"]'))
            result = module.evaluate(temp)
            self.assertIn('PREMATURE_EXTERNAL_CAPABILITY', result['errors'])

    def test_gateway_autostart_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = pathlib.Path(directory)
            for name in [*module.REQUIRED, 'cmd/skybind/main.go', 'module/service.sh']:
                dst = temp/name; dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT/name, dst)
            svc = temp/'module/service.sh'
            svc.write_text(svc.read_text() + '\n# unqualified r1-broker auto-start\n')
            self.assertIn('MODULE_AUTOSTARTS_UNQUALIFIED_BROKER', module.evaluate(temp)['errors'])

if __name__ == '__main__': unittest.main()
