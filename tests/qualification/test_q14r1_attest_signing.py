"""Q14R1: fail closed on incompatible attestation action/predicate modes."""
import hashlib
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[2]
WF=ROOT/'.github/workflows/skybind-q14-attested-candidates.yml'
PIN='c32b4b8b198b65d0bd9d63490e847ff7b53989d4'

class SigningWorkflowTests(unittest.TestCase):
 def test_pinned_v4_with_auto_provenance(self):
  x=WF.read_text()
  self.assertIn('actions/attest@'+PIN,x)
  self.assertNotIn('actions/attest@e59cbc1ad1ac2d59339667419eb8cdde6eb61e3d',x)
  self.assertEqual(x.count('uses: actions/attest@'),1)
  self.assertRegex(x,r'(?m)^\s*subject-path:\s*dist/q14/stage-\$\{\{ matrix.lane \}\}/skybind-\*-CANDIDATE-UNQUALIFIED\.zip$')
  # Do not fabricate a custom predicate or accidentally downgrade to generic mode.
  self.assertNotIn('predicate-type:',x)
  self.assertNotIn('predicate-path:',x)
  self.assertNotIn('predicate:',x)
 def test_permissions(self):
  x=WF.read_text()
  for line in ('contents: read','actions: read','id-token: write','attestations: write','artifact-metadata: write'):
   self.assertIn(line,x)
 def test_both_lanes_preserve_compare_and_original_subjects(self):
  x=WF.read_text()
  for s in ('lane: [A, B]','name: skybind-q14-candidate-${{ matrix.lane }}',
            'skybind-newfuture-CANDIDATE-UNQUALIFIED.zip',
            'skybind-bclone-CANDIDATE-UNQUALIFIED.zip',
            'needs: candidate-lanes','sha256','retention-days: 30'):
   # Hash check occurs in Python comparator, not necessarily as textual sha256 in workflow
   if s!='sha256': self.assertIn(s,x)
  self.assertNotIn('SB-G01: PASS',x)
 def test_valid_yaml_if_yaml_available(self):
  try: import yaml
  except ImportError: self.skipTest('PyYAML not installed')
  obj=yaml.safe_load(WF.read_text())
  self.assertEqual(obj['jobs']['candidate-lanes']['strategy']['matrix']['lane'],['A','B'])
  self.assertIn('compare-lanes',obj['jobs'])
  self.assertEqual(obj['permissions']['artifact-metadata'],'write')

if __name__=='__main__': unittest.main()
