from pathlib import Path
import json,subprocess,unittest
ROOT=Path(__file__).resolve().parents[2]
class G02Shell(unittest.TestCase):
    def test_local_check_without_external_attestation(self):
        p=subprocess.run(['bash',str(ROOT/'scripts/devtool/check_g02_state.sh')],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        x=json.loads(p.stdout)
        self.assertFalse(x['external_attestation_required'])
        self.assertEqual(x['policy'],'SKYBIND_PERSONAL_V1')
if __name__=='__main__':unittest.main()
