import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/dev/gates'))
import sb_cg1
class PersonalGates(unittest.TestCase):
    def test_gate_scope(self):
        r=sb_cg1.evaluate_all(ROOT)
        self.assertEqual(set(r['gates']),set(sb_cg1.GATES))
        self.assertFalse(r['external_attestation_required'])
        self.assertTrue(r['personal_scope_only'])
    def test_fresh_process_determinism(self):
        self.assertEqual(sb_cg1.evaluate_all(ROOT),sb_cg1.evaluate_all(ROOT))
if __name__=='__main__':unittest.main()
