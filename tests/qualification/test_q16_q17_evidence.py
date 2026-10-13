"""Q16/Q17 fail-closed tests: no G01/G02 gate input or release seal generated."""
import importlib.util, json, pathlib, tempfile, unittest
from unittest import mock
ROOT=pathlib.Path(__file__).resolve().parents[2]

def load(name):
 spec=importlib.util.spec_from_file_location(name,ROOT/'scripts/dev/release'/f'{name}.py')
 m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
Q16=load('q16_provider_evidence');Q17=load('q17_fixedpoint_runs')

class Q16Contract(unittest.TestCase):
 def test_invalid_run_identity_refused(self):
  for repo, runid in [('bad',5),('a/b',0),('../evil/x',1)]:
   with self.assertRaises(Q16.Blocked):Q16.run_metadata(repo,runid)
 def test_ci_failure_is_not_build_evidence(self):
  with mock.patch.object(Q16,'cmd',return_value=json.dumps({'id':13,'repository':{'full_name':'a/b'},'status':'completed','conclusion':'failure','head_sha':'a'*40,'path':Q16.WORKFLOW})):
   with self.assertRaisesRegex(Q16.Blocked,'identity'):Q16.run_metadata('a/b',13)
 def test_forged_duplicate_job_id_refused(self):
  responses=[json.dumps({'id':13,'repository':{'full_name':'a/b'},'status':'completed','conclusion':'success','head_sha':'a'*40,'path':Q16.WORKFLOW}),json.dumps({'jobs':[{'name':'pinned-provider-lanes (A)','id':123,'conclusion':'success'},{'name':'pinned-provider-lanes (B)','id':123,'conclusion':'success'}]})]
  with mock.patch.object(Q16,'cmd',side_effect=responses):
   with self.assertRaisesRegex(Q16.Blocked,'duplicate'):Q16.run_metadata('a/b',13)
 def test_original_upstream_archive_missing_refused(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=pathlib.Path(tmp)
   with self.assertRaises(Q16.Blocked):Q16.inspect(ROOT,path)
 def test_symlinked_raw_inputs_refused(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=pathlib.Path(tmp);a=root/'a';a.mkdir();(root/'b').symlink_to(a,target_is_directory=True)
   with self.assertRaises(Q16.Blocked):Q16.safe_dir(root/'b')
 def test_never_generates_gate_input(self):
  source=(ROOT/'scripts/dev/release/q16_provider_evidence.py').read_text()
  self.assertNotIn("'build/evidence/sb_g01_provider_builds.json'",source)
  self.assertIn("'gate_evidence_generated':False",source)

class Q17Contract(unittest.TestCase):
 def test_all_original_negative_names_covered(self):
  self.assertEqual(set(Q17.TESTS),Q17.sb_g02.REQUIRED_NEGATIVE)
 def test_missing_receipt_and_log_fail_closed(self):
  with tempfile.TemporaryDirectory() as temp:
   with self.assertRaises(Q17.Blocked):Q17.read(ROOT,pathlib.Path(temp))
 def test_identical_run_path_refused(self):
  with tempfile.TemporaryDirectory() as temp:
   p=pathlib.Path(temp)
   with self.assertRaisesRegex(Q17.Blocked,'distinct'):Q17.compare(ROOT,p,p)
 def test_tampered_log_refused(self):
  with tempfile.TemporaryDirectory() as temp:
   p=pathlib.Path(temp);checks={}
   for n,(pkg,test) in Q17.TESTS.items():
    (p/(n+'.log')).write_text('real test log')
    checks[n]={'package':pkg,'test':test,'passed':True,'result':'TEST_PASSED','log_sha256':Q17.sha(p/(n+'.log'))}
   record={'schema_version':1,'campaign':'SB-Q17','cases':checks,'status':'RAW_TESTS_PASSED_NOT_INDEPENDENT','errors':[]}
   (p/'receipt.json').write_text(json.dumps(record))
   self.assertEqual(Q17.read(ROOT,p)['status'],'RAW_TESTS_PASSED_NOT_INDEPENDENT')
   (p/'private_permissions.log').write_text('tampered')
   with self.assertRaisesRegex(Q17.Blocked,'tampered'):Q17.read(ROOT,p)
 def test_no_forged_independence(self):
  s=(ROOT/'scripts/dev/release/q17_fixedpoint_runs.py').read_text()
  self.assertIn("'devtool_identity_authenticated':False",s)
  self.assertIn("'independent_devtool_fixed_point_proven':False",s)
  self.assertNotIn('sb_g02_source.json',s.replace('Never writes sb_g02_source.json',''))

if __name__=='__main__':unittest.main()
