from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/dev/gates'))
import sb_g01
class G01PersonalTests(unittest.TestCase):
    def test_no_external_qualification_gate(self):
        x=sb_g01.evaluate(root=ROOT)
        self.assertEqual(x['policy'],'SKYBIND_PERSONAL_V1')
        self.assertFalse(x['external_attestation_required'])
        self.assertIn(x['status'],('PENDING_PERSONAL_CHECK','PERSONAL_EVIDENCE_PASS'))
if __name__=='__main__':unittest.main()
