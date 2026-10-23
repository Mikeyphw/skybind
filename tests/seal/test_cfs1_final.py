from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/dev/seal'))
import sb_cfs1
class PersonalSeal(unittest.TestCase):
    def test_eight_personal_sections(self):
        r=sb_cfs1.evaluate(ROOT)
        self.assertEqual(set(r['milestone_gates']),set(sb_cfs1.GATES))
        self.assertFalse(r['external_signature_required'])
        self.assertTrue(r['personal_scope_only'])
        self.assertIn(r['status'],('PERSONAL_RELEASE_PENDING','PERSONAL_RELEASE_APPROVED'))
    def test_readonly_determinism(self):
        self.assertEqual(sb_cfs1.evaluate(ROOT),sb_cfs1.evaluate(ROOT))
if __name__=='__main__':unittest.main()
