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

 def test_hidden_android_userhandle_api_is_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=pathlib.Path(tmp)
   for name in GATE.CHECKS:
    (root/name).parent.mkdir(parents=True,exist_ok=True)
    (root/name).write_bytes((ROOT/name).read_bytes())
   for name in ('cmd/skybind/main.go','docs/contracts/rclone-compat/SKYBIND_CONSUMER_ABI_V1.json'):
    (root/name).parent.mkdir(parents=True,exist_ok=True)
    (root/name).write_bytes((ROOT/name).read_bytes())
   authority=root/'android-app/app/src/main/java/io/github/mikeyphw/skybind/bridge/R1PackageManagerAuthority.kt'
   authority.write_text(authority.read_text()+'\n// BAD SDK use: userHandle.identifier\n')
   self.assertTrue(any(e.startswith('ANDROID_HIDDEN_USERHANDLE_API:') for e in GATE.check(root)['errors']))
   authority.write_bytes((ROOT/'android-app/app/src/main/java/io/github/mikeyphw/skybind/bridge/R1PackageManagerAuthority.kt').read_bytes())
   android_test=root/'android-app/app/src/androidTest/java/io/github/mikeyphw/skybind/R1PackageManagerAuthorityTest.kt'
   android_test.write_text(android_test.read_text().replace('accepted.copy(userId=accepted.userId+1),',''))
   self.assertIn('MISSING_WRONG_USER_NEGATIVE_TEST',GATE.check(root)['errors'])
