import importlib.util, json, pathlib, tempfile, unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('sb_g02',ROOT/'scripts/dev/gates/sb_g02.py')
M=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(M)
class GateG02Definition(unittest.TestCase):
 def test_g01_blocks_with_no_evidence(self):
  r=M.evaluate(g01_result={'status':'BLOCKED'})
  self.assertEqual(r['status'],'BLOCKED')
  self.assertEqual(r['final_seal'],'NOT_ISSUED')
  self.assertIn('SB-G01 is not source-qualified',r['reasons'])
 def test_cannot_pass_on_source_claim_only(self):
  r=M.evaluate(g01_result={'status':'SOURCE_BUILD_PASS'})
  self.assertEqual(r['status'],'BLOCKED')
  self.assertIn('missing independent Devtool validation receipts',r['reasons'])
 def test_fake_green_receipts_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'fake.json';p.write_text(json.dumps({'schema_version':1,'gate':'SB-G02','overlay_ids':list(M.REQUIRED_OVERLAYS),'fresh_devtool_runs':[{'run_id':'fake'}],'device_qualified':True,'final_seal':True,'warning_count':0}))
   r=M.evaluate(g01_result={'status':'SOURCE_BUILD_PASS'},evidence=p)
   self.assertEqual(r['status'],'BLOCKED')
   self.assertTrue(any('evidence' in s or 'incomplete' in s or 'drift' in s for s in r['reasons']))
 def test_canonical_api_must_match_embedded_bytes(self):
  self.assertEqual(M.digest(ROOT/M.SOURCES[0]),M.digest(ROOT/M.SOURCES[1]))
 def test_no_automatic_mount_qualification(self):
  r=M.evaluate(g01_result={'status':'BLOCKED'})
  self.assertEqual(r['android_device'],'NOT_ATTESTED')
  self.assertNotEqual(r['status'],'SOURCE_CONTROL_PASS')
if __name__=='__main__':unittest.main()
