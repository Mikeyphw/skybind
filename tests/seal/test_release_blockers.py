import json
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/dev/release-audit'))
import skybind_audit as audit

class SealDenials(unittest.TestCase):
  def test_no_release_without_device_or_upstream_pins(self):
    report=audit.blocked_report()
    self.assertEqual(report['status'],'BLOCKED')
    self.assertEqual(report['final_seal'],'NOT_ISSUED')
    self.assertEqual(len(report['milestone_gates']),8)
    self.assertIn('ANDROID_APP_VISIBILITY_NOT_ATTESTED',report['reasons'])
    self.assertIn('NEWFUTURE_ARCHIVE_SHA256_UNPINNED',report['reasons'])
  def test_invalid_repository_is_blocked_not_passed(self):
    with tempfile.TemporaryDirectory() as t:
      report=audit.blocked_report(Path(t))
      self.assertEqual(report['status'],'BLOCKED')
      self.assertIn('PROVIDER_LOCK_UNTRUSTWORTHY',report['reasons'])
      self.assertIn('CAMPAIGN_INDEX_INVALID',report['reasons'])
if __name__=='__main__':unittest.main()
