import importlib.util
import pathlib
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('r1_device_trust_gate',ROOT/'scripts/dev/android/r1_device_trust_source_gate.py')
GATE=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)

class DeviceTrustSource(unittest.TestCase):
 def test_current_has_no_implicit_privileged_activation(self):
  out=GATE.check()
  self.assertEqual(out['status'],'PASS_R1_DEVICE_TRUST_SOURCE_NO_EXTERNAL_ACTIVATION',out)
  self.assertFalse(out['production_listener_enabled'])
  self.assertFalse(out['grants_issued'])
  self.assertFalse(out['external_provider_qualified'])
 def test_claiming_external_support_fails_closed(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=pathlib.Path(tmp)
   for name in GATE.CHECKS:
    (root/name).parent.mkdir(parents=True,exist_ok=True)
    (root/name).write_bytes((ROOT/name).read_bytes())
   for name in ('cmd/skybind/main.go','docs/contracts/rclone-compat/SKYBIND_CONSUMER_ABI_V1.json'):
    (root/name).parent.mkdir(parents=True,exist_ok=True)
    (root/name).write_bytes((ROOT/name).read_bytes())
   config=root/'docs/contracts/rclone-compat/SKYBIND_CONSUMER_ABI_V1.json'
   config.write_text(config.read_text().replace('"available_external_capabilities": []','"available_external_capabilities": ["rclone.version"]'))
   self.assertIn('PREMATURE_EXTERNAL_CAPABILITY_ADVERTISEMENT',GATE.check(root)['errors'])
   main=root/'cmd/skybind/main.go'
   main.write_text(main.read_text()+'\n// ConsumerSocket auto-start')
   self.assertIn('R1_PRODUCTION_ACTIVATION_NOT_QUALIFIED',GATE.check(root)['errors'])
