import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/dev/release'))
import skybind_release as rel

class SecurityInvariants(unittest.TestCase):
 def test_archive_entry_and_symlink_denial(self):
  for name in ('../outside','/root/.ssh/key','safe/../evil','windows\\escape','a//b','a/./b','a/'):
   self.assertFalse(rel.safe_path(name))
  for name in ('module.prop','webroot/app.js','system/bin/skybind'):
   self.assertTrue(rel.safe_path(name))
 def test_upstream_runtime_no_selector_or_installed_download(self):
  source=(ROOT/'scripts/dev/runtime/skybind_runtime.py').read_text()
  assert 'build-time-only' in source
  assert 'archive_sha256' in source
  assert 'is_arm64_elf' in source
  assert 'GOTOOLCHAIN' in source
  release=(ROOT/'scripts/dev/release/skybind_release.py').read_text()
  assert 'CANDIDATE_ONLY_NOT_SEALED' in release
  assert 'verify_package(runtime)' in release
 def test_device_probe_no_privileged_permission_or_shell_claim(self):
  manifest=(ROOT/'tests/device/probe-app/app/src/main/AndroidManifest.xml').read_text()
  assert 'MANAGE_EXTERNAL_STORAGE' not in manifest
  assert 'uses-permission' not in manifest
  probe=(ROOT/'tests/device/probe-app/app/src/main/java/org/skybind/probe/ProbeActivity.java').read_text()
  assert 'Process.myUid()' in probe and 'new FileOutputStream' in probe
  assert 'FileInputStream' in probe and 'read_matches' in probe
  assert 'Runtime.getRuntime()' not in probe
if __name__=='__main__':unittest.main()
