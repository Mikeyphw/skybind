from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/dev/gates'))
import sb_g02
class G02PersonalTests(unittest.TestCase):
    def test_local_qualifier(self):
        x=sb_g02.evaluate(root=ROOT)
        self.assertEqual(x['policy'],'SKYBIND_PERSONAL_V1')
        self.assertFalse(x['external_attestation_required'])
        self.assertIn(x['status'],('PENDING_PERSONAL_CHECK','PERSONAL_EVIDENCE_PASS'))
    def test_catalogs_equal(self):
        self.assertEqual(sb_g02.digest(ROOT/sb_g02.SOURCES[0]),sb_g02.digest(ROOT/sb_g02.SOURCES[1]))
if __name__=='__main__':unittest.main()
