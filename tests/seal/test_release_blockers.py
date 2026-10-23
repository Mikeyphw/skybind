"""C06 personal release audit: no independently signed gate required."""
from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/dev/release-audit'))
import skybind_audit
class ReleaseAudit(unittest.TestCase):
 def test_personal_gate_inventory(self):
  d=skybind_audit.evaluate(ROOT)
  self.assertEqual(d['policy'],'SKYBIND_PERSONAL_V1')
  self.assertFalse(d['external_qualification_required'])
  self.assertEqual(len(d['milestone_gates']),8)
 def test_missing_authorization_is_not_approved(self):
  d=skybind_audit.evaluate(ROOT)
  self.assertIn(d['status'],('PERSONAL_RELEASE_PENDING','PERSONAL_RELEASE_APPROVED'))
  self.assertEqual(d['owner_approval'],d['status']=='PERSONAL_RELEASE_APPROVED')
 def test_readonly_repeatability(self):
  self.assertEqual(skybind_audit.evaluate(ROOT),skybind_audit.evaluate(ROOT))
if __name__=='__main__':unittest.main()
