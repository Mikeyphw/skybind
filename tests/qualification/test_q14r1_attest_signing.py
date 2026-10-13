"""Historical Q14R1 check superseded by private-repository Q14R2 signing."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[2]
class ReplacedGitHubAttestTests(unittest.TestCase):
 def test_private_repo_does_not_require_unavailable_github_attestation_service(self):
  wf=(ROOT/'.github/workflows/skybind-q14-attested-candidates.yml').read_text()
  self.assertNotIn('actions/attest@',wf)
  self.assertIn('SKYBIND_Q14_ED25519_KEY_B64',wf)
  self.assertIn('candidate-provenance.ed25519', (ROOT/'scripts/dev/release/q14_private_signing.py').read_text())
 def test_release_seal_unmodified(self):
  script=(ROOT/'scripts/dev/release/q14_attestation.py').read_text()
  self.assertIn("'final_seal': 'NOT_ISSUED'",script)
  self.assertIn("'independent_attestation': False",script)

if __name__=='__main__':unittest.main()
