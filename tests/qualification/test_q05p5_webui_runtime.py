"""Display actual native runtime failure reasons without weakening integrity or sealing."""
import json
import pathlib
import shutil
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
NODE = shutil.which('node')

@unittest.skipUnless(NODE, 'Node required for WebUI runtime diagnostics')
class RuntimeErrorPresentation(unittest.TestCase):
    def test_rendered_runtime_reason_from_native_status(self):
        # Import the pure production helper, not a duplicate implementation.
        helper = (ROOT/'module/webroot/parity.js').resolve().as_uri()
        script = f"""
          import assert from 'node:assert/strict';
          import {{runtimePresentation,runtimeFailureText}} from {json.dumps(helper)};
          const native = {{provider:'',ready:false,reason:'invalid manifest inventory',provenance_available:false,provenance_valid:false}};
          const status = runtimePresentation(native);
          assert.equal(status.operational, false);
          assert.equal(runtimeFailureText(status), 'Runtime integrity not verified: invalid manifest inventory');
          assert.equal(status.issues[0], 'invalid manifest inventory');
          const hashMismatch = runtimePresentation({{...native,reason:'system/bin/rclone: sha256 mismatch'}});
          assert.match(runtimeFailureText(hashMismatch), /sha256 mismatch/);
          assert.equal(runtimeFailureText(runtimePresentation({{...native,provider:'bclone',ready:true,reason:'on-disk hashes verified; FUSE device untested',provenance_valid:true}})), '');
          assert.match(runtimeFailureText(runtimePresentation({{...native,reason:''}})), /Backend did not provide/);
          assert.equal(runtimeFailureText({{reason:'broken\\nmanifest\\u0000path',operational:false}}), 'Runtime integrity not verified: broken manifest path');
          assert.ok(runtimeFailureText({{reason:'x'.repeat(400),operational:false}}).length < 300);
          console.log('runtime diagnostic presentation PASS');
        """
        result = subprocess.run([NODE, '--input-type=module', '-e', script], capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_real_ui_consumes_reason_in_home_and_runtime(self):
        app = (ROOT/'module/webroot/app.js').read_text()
        self.assertIn('const runtimeFailure = runtimeFailureText(runtime);',app)
        self.assertIn('if (runtimeFailure) issues.push(runtimeFailure);',app)
        self.assertIn("text('homeRuntimeDetail', runtimeFailure ||",app)
        self.assertIn("metric(grid,'Integrity failure',runtimeFailure)",app)
        self.assertIn('const runtimeMessage=runtimeFailureText(runtime) ||',app)
        self.assertIn('function showHomeLoadFailure(error)',app)
        self.assertIn("text('homeSummary', message)",app)
        self.assertIn("if(view==='home')showHomeLoadFailure(error)",app)
        self.assertIn("if(state.activeView==='home')showHomeLoadFailure(error)",app)
        workflow=(ROOT/'.github/workflows/skybind-candidate-integration.yml').read_text()
        self.assertIn("test_q05p5_webui_runtime.py' -v",workflow)
        self.assertLess(workflow.index('test_q05p5_webui_runtime.py'), workflow.index('Build and independently verify both complete source-only candidates'))

    def test_webui_payload_parse_valid_and_no_authority_change(self):
        for path in sorted((ROOT/'module/webroot').glob('*.js')):
            with self.subTest(source=path.name):
                r=subprocess.run([NODE,'--input-type=module','--check'],input=path.read_text(),text=True,capture_output=True)
                self.assertEqual(r.returncode,0,r.stderr)
        selection=json.loads((ROOT/'scripts/dev/runtime/source.selection.json').read_text())
        self.assertEqual(selection['gate_g01'],'BLOCKED')
        self.assertEqual(selection['final_seal'],'NOT_ISSUED')
        self.assertFalse(selection['independent_attestation'])

if __name__=='__main__': unittest.main()
