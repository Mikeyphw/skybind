import importlib.util
from pathlib import Path
import tempfile,unittest,json
p=Path(__file__).resolve().parents[2]/'scripts/dev/gates/sb_g01.py'
s=importlib.util.spec_from_file_location('sb_g01',p);g=importlib.util.module_from_spec(s);s.loader.exec_module(g)
class GateTests(unittest.TestCase):
 def test_current_gate_blocked(self):
  result=g.evaluate();self.assertEqual(result['status'],'BLOCKED');self.assertEqual(result['android_device'],'NOT_ATTESTED')
 def test_fake_evidence_cannot_pass(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);l=root/'scripts/dev/runtime/source.lock.json';l.parent.mkdir(parents=True);l.write_text(json.dumps({'newfuture':{'archive_sha256':'0'*64},'bclone':{'commit':'a'*40,'ndk_revision':'x','go_version':'go version x'}}))
   evidence=root/'evidence.json';evidence.write_text(json.dumps({'schema_version':1,'qualification':'REAL_PINNED_PROVIDER_BUILD','source_lock_sha256':g.sha(l),'overlay_ids':list(g.REQUIRE),'providers':{},'device_qualification':False}))
   result=g.evaluate(evidence,root)
   self.assertEqual(result['status'],'BLOCKED')
   self.assertTrue(any('requires independent' in x for x in result['reasons']))
if __name__=='__main__':unittest.main()
