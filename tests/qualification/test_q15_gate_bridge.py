"""SB-Q15 no-promotion, integrity, and trust-boundary regressions."""
import importlib.util
import json
from pathlib import Path
from unittest import TestCase, mock
import tempfile
import subprocess
import shutil
import unittest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('q15_gate_bridge',ROOT/'scripts/dev/release/q15_gate_bridge.py')
q15=importlib.util.module_from_spec(spec);spec.loader.exec_module(q15)

class Q15Tests(TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
  self.root=Path(self.t.name)/'source';self.root.mkdir();self.staging=Path(self.t.name)/'ci';self.staging.mkdir()
  self.key=Path(self.t.name)/'trust.pem';self.key.write_text('trusted-key')
  self.report={'schema_version':1,'campaign':'SB-Q14','final_seal':'NOT_ISSUED',
   'independent_attestation':False,'private_ci_signatures_verified':True,'all_four_attested':False,
   'run':{'repository':'Mikeyphw/skybind','head_sha':'a'*40,'run_id':38336604093,
     'run_attempt':1,'workflow':'skybind-q14-attested-candidates.yml',
     'metadata_source':'AUTHENTICATED_GITHUB_API','conclusion':'success'},
   'lanes':{},'signed_candidate_provenance':{}}
  self.members={'system/bin/skybind':'a'*64,'system/bin/rclone':'b'*64,
     'system/vendor/bin/fusermount3':'c'*64,'runtime.provenance.json':'d'*64}
  self.lanes={}
  for lab in ['A','B']:
   stage=self.staging/('lane-'+lab);stage.mkdir()
   for name in q15.EXACT_LANE_FILES:(stage/name).write_bytes(b'x')
   providers={p:{'status':'VALID_UNQUALIFIED_CANDIDATE','sha256':('a' if p=='bclone' else 'b')*64,'members':self.members} for p in ('bclone','newfuture')}
   self.lanes[lab]={'status':'VALID_UNQUALIFIED_LANE','providers':providers,
      'build_source':{'commit':'a'*40}}
   self.report['lanes'][lab]={'providers':json.loads(json.dumps(providers))}
   self.report['signed_candidate_provenance'][lab]={p:{'candidate_sha256':providers[p]['sha256'],
      'public_key_sha256':'f'*64,'status':'PRIVATE_ED25519_SIGNATURE_VERIFIED_NOT_CFS1'} for p in ('bclone','newfuture')}
 def fake_inspect(self,path,root):return self.lanes[path.name[-1]]
 def check(self,report=None,github=False):
  with mock.patch.object(q15,'verify_private',return_value={'status':'PRIVATE_ED25519_SIGNATURE_VERIFIED_NOT_CFS1',
      'public_key_sha256':'f'*64,'subjects_sha256':{'candidate-evidence.json':'c'*64}}),\
       mock.patch.object(q15.q13,'inspect_lane',side_effect=self.fake_inspect):
   return q15.crosscheck_q14(self.root,report or self.report,self.staging,self.key,github_identity=github)
 def test_owner_signatures_do_not_promote_gates(self):
  res=self.check()
  self.assertFalse(res['independent_build_custody']);self.assertFalse(res['cfs1_gate_evidence'])
  self.assertEqual(res['status'],'OWNER_SIGNED_CANDIDATES_REVERIFIED_NOT_INDEPENDENT')
 def test_ci_is_only_recorded_by_default(self):
  self.assertEqual(self.check()['ci_identity'],'RECORDED_FROM_Q14_NOT_FRESHLY_AUTHENTICATED')
 def test_fresh_api_identity_required_when_requested(self):
  import q14_attestation
  good=self.report['run'].copy()
  with mock.patch.object(q14_attestation,'authenticated_run',return_value=good):
   self.assertEqual(self.check(github=True)['ci_identity'],'REAUTHENTICATED_GITHUB_API')
  good['head_sha']='b'*40
  with mock.patch.object(q14_attestation,'authenticated_run',return_value=good):
   with self.assertRaisesRegex(ValueError,'IDENTITY_DRIFT'):self.check(github=True)
 def test_rejects_modified_candidate_claim(self):
  self.report['lanes']['A']['providers']['bclone']={'sha256':'z'*64}
  with self.assertRaisesRegex(ValueError,'BYTES_MISMATCH'):self.check()
 def test_rejects_substituted_public_key_claim(self):
  self.report['signed_candidate_provenance']['B']['bclone']['public_key_sha256']='0'*64
  with self.assertRaisesRegex(ValueError,'SIGNATURE_MISMATCH'):self.check()
 def test_rejects_unsigned_claim(self):
  self.report['private_ci_signatures_verified']=False
  with self.assertRaisesRegex(ValueError,'NOT_VALID'):self.check()
 def test_rejects_false_final_seal(self):
  self.report['final_seal']='QUALIFIED'
  with self.assertRaisesRegex(ValueError,'REPORT_IDENTITY'):self.check()
 def test_rejects_false_independent_attestation(self):
  self.report['independent_attestation']=True
  with self.assertRaisesRegex(ValueError,'REPORT_IDENTITY'):self.check()
 def test_rejects_wrong_github_repo_shape(self):
  self.report['run']['repository']='foo bar'
  with self.assertRaisesRegex(ValueError,'RUN_IDENTITY'):self.check()
 def test_rejects_extra_lane_file(self):
  (self.staging/'lane-A'/'extra').write_bytes(b'data')
  with self.assertRaisesRegex(ValueError,'LANE_FILE_SET'):self.check()
 def test_rejects_linked_lane_file(self):
  p=self.staging/'lane-B'/'candidate-evidence.json';p.unlink();p.symlink_to(self.key)
  with self.assertRaisesRegex(ValueError,'LANE_FILE_SET'):self.check()
 def test_rejects_key_inside_artifacts(self):
  key=self.staging/'key.pem';key.write_bytes(b'trust')
  with self.assertRaisesRegex(ValueError,'KEY_FROM_ARTIFACT'):q15.crosscheck_q14(self.root,self.report,self.staging,key)
 def test_rejects_wrong_source(self):
  self.lanes['B']['build_source']['commit']='0'*40
  with self.assertRaisesRegex(ValueError,'BUILD_SOURCE'):self.check()
 def test_rejects_mismatched_provider_hash(self):
  self.lanes['B']['providers']['bclone']={'sha256':'0'*64,'members':self.members,'status':'VALID_UNQUALIFIED_CANDIDATE'}
  with self.assertRaisesRegex(ValueError,'BYTES_MISMATCH'):self.check()
 def test_never_writes_over_symlink_report(self):
  dest=self.root/'target';dest.write_text('keep')
  (self.root/'skybind-q15-summary.json').symlink_to(dest)
  with self.assertRaisesRegex(ValueError,'SYMLINK'):q15.safe_write(self.root,'skybind-q15-summary.json',b'evil')
  self.assertEqual(dest.read_text(),'keep')
 def test_checked_json_rejects_link(self):
  f=self.root/'real.json';f.write_text('{}');link=self.root/'link.json';link.symlink_to(f)
  with self.assertRaisesRegex(ValueError,'LINKED'):q15.checked_json(link)
 def test_report_explicitly_separates_independence(self):
  data={'owner_signed_ci':{'status':'OWNER_SIGNED_CANDIDATES_REVERIFIED_NOT_INDEPENDENT'},
    'gate_contracts':{'SB-G01':{'actual':'BLOCKED','actual_reasons':['not independent']}},
    'errors':[],'next_actions':['Do not forge evidence']}
  text=q15.markdown(data)
  self.assertIn('NOT_ISSUED',text);self.assertIn('BLOCKED',text)
  self.assertIn('Do not forge evidence',text)

if __name__=='__main__':unittest.main()
