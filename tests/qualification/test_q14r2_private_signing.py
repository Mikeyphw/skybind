"""SB-Q14R2: private repo signing never calls GitHub attestation API."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'scripts/dev/release/q14_private_signing.py'
spec=importlib.util.spec_from_file_location('q14_private_signing',SRC)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
WF=(ROOT/'.github/workflows/skybind-q14-attested-candidates.yml').read_text()
IDENT={'lane':'A','repo':'Mikeyphw/skybind','head_sha':'a'*40,'run_id':38334898423,'attempt':2}

@unittest.skipUnless(shutil.which('openssl'),'OpenSSL not installed')
class PrivateManifestTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.p=Path(self.tmp.name);self.stage=self.p/'stage';self.stage.mkdir()
  for x in mod.SUBJECT_NAMES:
   (self.stage/x).write_bytes(('test:'+x).encode())
  self.key=self.p/'private.pem'
  subprocess.run(['openssl','genpkey','-algorithm','ED25519','-out',str(self.key)],check=True,capture_output=True)
  self.pub=self.stage/mod.PUBLIC
 def signing(self):
  return mod.sign(self.stage,self.key,**IDENT)
 def checked(self,**overrides):
  args=dict(IDENT);args.update(overrides)
  return mod.verify(self.stage,self.pub,**args)
 def test_signature_valid_for_exact_original_subjects_and_identity(self):
  self.signing();self.assertEqual(self.checked()['status'],'PRIVATE_ED25519_SIGNATURE_VERIFIED_NOT_CFS1')
  self.assertEqual(json.loads((self.stage/mod.MANIFEST).read_text())['final_seal'],'NOT_ISSUED')
 def test_tampering_each_subject_fails(self):
  for x in mod.SUBJECT_NAMES:
   with self.subTest(x=x):
    self.stage.joinpath(x).write_bytes(b'original')
    if not self.pub.exists(): self.signing()
    self.stage.joinpath(x).write_bytes(b'altered')
    with self.assertRaises(ValueError): self.checked()
    for name in (mod.MANIFEST,mod.SIGNATURE,mod.PUBLIC): (self.stage/name).unlink()
 def test_wrong_run_sha_lane_attempt_or_repo_fails(self):
  self.signing()
  for delta in ({'run_id':4},{'attempt':3},{'lane':'B'},{'head_sha':'b'*40},{'repo':'Other/repo'}):
   with self.subTest(delta=delta),self.assertRaises(ValueError): self.checked(**delta)
 def test_modified_signature_fails(self):
  self.signing();(self.stage/mod.SIGNATURE).write_bytes(b'bad signature')
  with self.assertRaises(ValueError):self.checked()
 def test_substituted_key_rejected(self):
  self.signing();second=self.p/'other.pem';pub=self.p/'other-public.pem'
  subprocess.run(['openssl','genpkey','-algorithm','ED25519','-out',str(second)],check=True,capture_output=True)
  subprocess.run(['openssl','pkey','-in',str(second),'-pubout','-out',str(pub)],check=True,capture_output=True)
  with self.assertRaisesRegex(ValueError,'TRUST_ANCHOR'):mod.verify(self.stage,pub,**IDENT)
 def test_no_sign_overwrite(self):
  self.signing()
  with self.assertRaisesRegex(ValueError,'ALREADY_EXISTS'):self.signing()
 def test_keyless_workflow_not_requested(self):
  self.assertNotIn('uses: actions/attest@',WF)
  self.assertNotIn('attestations: write',WF)
  self.assertNotIn('id-token: write',WF)
  self.assertIn('secrets.SKYBIND_Q14_ED25519_KEY_B64',WF)
  self.assertIn('vars.SKYBIND_Q14_SIGNER_PUBLIC_SHA256',WF)
  self.assertIn('--trusted-public-key received/skybind-q14-candidate-A/candidate-signer-public.pem',WF)
  self.assertIn('matrix.lane',WF)
  self.assertIn('candidate-evidence.json',WF)
  self.assertIn('NOT A RELEASE',WF)
  self.assertNotIn('SB-G01: PASS',WF)

if __name__=='__main__':unittest.main()
