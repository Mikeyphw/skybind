"""Q05P4 ES-module syntax gate and regression: source checks only, no device attestation."""
import pathlib, shutil, subprocess, tempfile, unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]
WEBROOT=ROOT/'module/webroot'
NODE=shutil.which('node')
BAD="byId('cryptBackdrop')?.addEventListener('click',(event)=>{if(event.target===byId('cryptBackdrop'))closeCryptCreator();});});byId('jobBackdrop')"
GOOD=BAD.replace('});});byId','});byId')

@unittest.skipUnless(NODE, 'Node required for WebUI ESM syntax gate')
class WebUISyntax(unittest.TestCase):
 def run_check(self,code):
  return subprocess.run([NODE,'--input-type=module','--check'],input=code,text=True,capture_output=True)
 def test_all_packaged_js_are_parseable_es_modules(self):
  files=sorted(WEBROOT.glob('*.js'))
  self.assertEqual([p.name for p in files],['app.js','bridge.js','flow.js','model.js','parity.js'])
  for p in files:
   with self.subTest(module=p.name):
    r=self.run_check(p.read_text())
    self.assertEqual(r.returncode,0,r.stderr)
 def test_original_bad_closure_is_rejected(self):
  clean=(WEBROOT/'app.js').read_text()
  self.assertIn(GOOD,clean)
  self.assertNotIn(BAD,clean)
  self.assertIn('void bootstrap();',clean)
  broken=clean.replace(GOOD,BAD,1)
  r=self.run_check(broken)
  self.assertNotEqual(r.returncode,0)
  self.assertIn('SyntaxError',r.stderr)
 def test_repaired_entrypoint_is_valid_and_orig_nexus_reference_is_valid(self):
  nexus=ROOT/'tests/fixtures/webui-reference/raw/app.js'
  self.assertEqual(self.run_check(nexus.read_text()).returncode,0)
  self.assertEqual(self.run_check((WEBROOT/'app.js').read_text()).returncode,0)
 def test_ci_checks_real_module_syntax_before_build(self):
  ci=(ROOT/'.github/workflows/skybind-candidate-integration.yml').read_text()
  self.assertIn('Validate packaged WebUI ES module syntax (fail CLOSED)',ci)
  self.assertIn('node --input-type=module --check < "$source"',ci)
  self.assertLess(ci.index('Validate packaged WebUI ES module syntax'),ci.index('Build and independently verify both complete source-only candidates'))
 def test_skybind_bridge_is_unchanged_from_q05p3_contract(self):
  text=(WEBROOT/'bridge.js').read_text()
  self.assertIn('globalThis.ksu.exec(command, JSON.stringify({}), callback)',text)
  self.assertIn("const EMBEDDED_BINARY = '/data/adb/modules/skybind/system/bin/skybind';",text)

if __name__=='__main__': unittest.main()
