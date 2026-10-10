"""Final seal: no green on missing gates, untrusted evidence, or claimed source success."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/dev/seal'))
import sb_cfs1 as final

class FinalSealDenials(unittest.TestCase):
 def _no_trust(self):
  return patch.dict(os.environ,{'SKYBIND_FINAL_SEAL_EVIDENCE_DIR':'',
      'SKYBIND_FINAL_SEAL_PUBKEY':'','SKYBIND_FINAL_SEAL_PUBKEY_SHA256':''})
 def test_eight_gates_and_57_operations_closed(self):
  with self._no_trust(): obj=final.evaluate(ROOT)
  self.assertEqual(set(obj['milestone_gates']),set(final.GATES))
  self.assertEqual(obj['status'],'BLOCKED')
  self.assertEqual(obj['final_seal'],'NOT_ISSUED')
  self.assertIsNone(obj['final_attestation_sha256'])
  self.assertIn('FINAL_GATE_BLOCKED_SB-G01',obj['reasons'])
  self.assertIn('FINAL_GATE_BLOCKED_SB-G08',obj['reasons'])
  self.assertEqual(len(json.loads((ROOT/'internal/control/operations.json').read_text())['operations']),57)
 def test_final_auditor_readonly_and_deterministic(self):
  files=[ROOT/'internal/control/control.go', ROOT/'scripts/dev/gates/sb_cg1.py']
  before=[final.sha(x.read_bytes()) for x in files]
  with self._no_trust():
   a=final.evaluate(ROOT);b=final.evaluate(ROOT)
  self.assertEqual(a,b)
  self.assertEqual(before,[final.sha(x.read_bytes()) for x in files])
 def test_cli_blocked_returns_distinct_code(self):
  env={**os.environ,'SKYBIND_FINAL_SEAL_EVIDENCE_DIR':'','SKYBIND_FINAL_SEAL_PUBKEY':'','SKYBIND_FINAL_SEAL_PUBKEY_SHA256':''}
  p=subprocess.run([sys.executable,str(ROOT/'scripts/dev/seal/sb_cfs1.py')],env=env,capture_output=True,text=True,timeout=20)
  self.assertEqual(p.returncode,3,p.stderr)
  d=json.loads(p.stdout)
  self.assertEqual(d['final_seal'],'NOT_ISSUED')
 def test_inrepo_signed_material_never_qualifies(self):
  with tempfile.TemporaryDirectory() as d:
   key=Path(d)/'key.pub';key.write_text('junk')
   env={'SKYBIND_FINAL_SEAL_EVIDENCE_DIR':str(ROOT/'docs'),
        'SKYBIND_FINAL_SEAL_PUBKEY':str(key),
        'SKYBIND_FINAL_SEAL_PUBKEY_SHA256':final.sha(key.read_bytes())}
   with patch.dict(os.environ,env):
    reasons,digest=final._verify_final_attestation(ROOT,commit='a'*40,digest='b'*40,gate_results={})
   self.assertEqual(reasons,['FINAL_EVIDENCE_OR_KEY_INSIDE_REPOSITORY'])
   self.assertIsNone(digest)
 def test_wrong_pinned_trust_key_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   key=Path(d)/'key.pub';key.write_text('junk')
   with patch.dict(os.environ,{
     'SKYBIND_FINAL_SEAL_EVIDENCE_DIR':d,
     'SKYBIND_FINAL_SEAL_PUBKEY':str(key),
     'SKYBIND_FINAL_SEAL_PUBKEY_SHA256':'0'*64}):
    reasons,digest=final._verify_final_attestation(ROOT,commit='a'*40,digest='b'*40,gate_results={})
   self.assertEqual(reasons,['FINAL_TRUST_KEY_PIN_INVALID'])
   self.assertIsNone(digest)
 def test_absent_signature_rejected_even_with_correct_key_pin(self):
  with tempfile.TemporaryDirectory() as d:
   key=Path(d)/'key.pub';key.write_text('junk')
   with patch.dict(os.environ,{
     'SKYBIND_FINAL_SEAL_EVIDENCE_DIR':d,
     'SKYBIND_FINAL_SEAL_PUBKEY':str(key),
     'SKYBIND_FINAL_SEAL_PUBKEY_SHA256':final.sha(key.read_bytes())}):
    reasons,_=final._verify_final_attestation(ROOT,commit='a'*40,digest='b'*40,gate_results={})
   self.assertEqual(reasons,['FINAL_SIGNED_ATTESTATION_MISSING'])
 def test_missing_critical_gate_not_bypassed_with_attestation(self):
  with self._no_trust(),patch.object(final,'_verify_final_attestation',return_value=([], 'f'*64)):
   d=final.evaluate(ROOT)
  self.assertEqual(d['status'],'BLOCKED')
  self.assertEqual(d['final_seal'],'NOT_ISSUED')
  self.assertIsNone(d['final_attestation_sha256'])
 def test_evidence_path_filename_policy(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);base=root/'evidence';base.mkdir();(base/'proof.json').write_text('{}')
   self.assertEqual(final._external_file(ROOT,base,'proof.json'),base/'proof.json')
   for name in ('../proof.json','../../passwd','a/b','..',''):
    with self.subTest(name=name), self.assertRaises(ValueError):
     final._external_file(ROOT,base,name)
 def test_source_inventory_fails_closed(self):
  with tempfile.TemporaryDirectory() as d,self._no_trust():
   result=final.evaluate(Path(d))
   self.assertEqual(result['status'],'BLOCKED')
   self.assertEqual(result['final_seal'],'NOT_ISSUED')
   self.assertTrue(any('FINAL_SOURCE' in e for e in result['reasons']))
 def test_valid_signature_fixture_and_tamper_rejection(self):
  # Test-only ephemeral signer: confirms real signature verification, never a
  # product release attestation and never written into the Git repository.
  if subprocess.run(['sh','-c','command -v openssl >/dev/null'],capture_output=True).returncode:
   self.skipTest('OpenSSL unavailable')
  with tempfile.TemporaryDirectory() as t:
   base=Path(t);(base/'artifacts').mkdir();(base/'receipts').mkdir()
   private=base/'test-only-key.pem';public=base/'test-only-key.pub'
   subprocess.run(['openssl','genpkey','-algorithm','Ed25519','-out',str(private)],check=True,capture_output=True)
   subprocess.run(['openssl','pkey','-in',str(private),'-pubout','-out',str(public)],check=True,capture_output=True)
   commit='b'*40; tree='c'*40
   candidate=base/'artifacts'/'skybind-candidate.zip';candidate.write_bytes(b'fixture-only')
   receipts=[]
   for gate in final.GATES:
    name=gate+'.json';file=base/'receipts'/name
    file.write_text(json.dumps({'gate':gate,'status':final.EXPECTED[gate],
      'source_commit':commit,'source_tree_sha256':tree}))
    receipts.append({'gate':gate,'filename':name,'sha256':final.sha(file.read_bytes())})
   data={'schema_version':1,'product':'skybind','source_commit':commit,
    'source_tree_sha256':tree,'result':'QUALIFIED','open_critical_obligations':[],
    'warnings':0,'milestone_results':final.EXPECTED,
    'evidence_kinds':sorted(final.REQUIRED_EVIDENCE),'independent_receipts':receipts,
    'candidate':{'filename':candidate.name,'sha256':final.sha(candidate.read_bytes())}}
   attestation=base/'final-attestation.json';attestation.write_text(json.dumps(data,sort_keys=True))
   subprocess.run(['openssl','pkeyutl','-sign','-inkey',str(private),'-rawin',
                   '-in',str(attestation),'-out',str(base/'final-attestation.sig')],check=True,capture_output=True)
   env={'SKYBIND_FINAL_SEAL_EVIDENCE_DIR':str(base),
        'SKYBIND_FINAL_SEAL_PUBKEY':str(public),
        'SKYBIND_FINAL_SEAL_PUBKEY_SHA256':final.sha(public.read_bytes())}
   with patch.dict(os.environ,env):
    reasons,digest=final._verify_final_attestation(ROOT,commit=commit,digest=tree,gate_results=final.EXPECTED)
    self.assertEqual(reasons,[])
    self.assertEqual(digest,final.sha(attestation.read_bytes()))
    candidate.write_bytes(b'tampered!')
    reasons,digest=final._verify_final_attestation(ROOT,commit=commit,digest=tree,gate_results=final.EXPECTED)
    self.assertIn('FINAL_CANDIDATE_CHECKSUM_MISMATCH',reasons)
    self.assertIsNone(digest)
 def test_present_validator_never_contains_key_generation(self):
  code=(ROOT/'scripts/dev/seal/sb_cfs1.py').read_text()
  for word in ('genpkey','openssl req','sign -inkey','BEGIN PRIVATE KEY'):
   self.assertNotIn(word,code)

if __name__=='__main__':unittest.main()
