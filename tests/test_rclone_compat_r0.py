"""R0 non-executable negative tests; device and compatibility parity not claimed."""
import importlib.util
import json
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/dev/provider/rclone_compat_r0.py'
spec = importlib.util.spec_from_file_location('skybind_r0', SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class R0Contract(unittest.TestCase):
    def test_matrix_intentionally_disables_runtime(self):
        doc=mod.load_contract()
        self.assertFalse(doc['constraints']['runtime_invocation_enabled'])
        self.assertTrue(all(c['runtime_qualified'] is False for c in doc['commands'].values()))
    def test_all_declared_commands_are_non_executable(self):
        commands=mod.load_contract()['commands']
        for name, spec in commands.items():
            args=[name]+(['restic'] if name=='serve' else ['drive:folder']*len(spec['positional']))
            if name=='serve':args.append('--stdio')
            with self.subTest(name=name):
                self.assertEqual(mod.inspect(args)['status'],'DECLARED_NOT_IMPLEMENTED')
    def test_bkx_parity_shape_examples(self):
        args=[
         ['version','--config','/app/readable.ini'],
         ['lsjson','drive:folder','--max-depth','1','--no-mimetype','--config','/tmp/view'],
         ['lsjson','drive:file','--stat','--no-mimetype'],
         ['lsjson','drive:folder','--recursive','--files-only','--no-mimetype'],
         ['size','drive:folder','--json'],
         ['copy','drive:src','drive:dst','--use-json-log','--stats','500ms','--stats-log-level','NOTICE','--log-level','NOTICE','--retries','3','--low-level-retries','5','--ignore-existing'],
         ['copyto','drive:src','drive:dst','--immutable'],
         ['sync','drive:src','drive:dst','--max-delete','37'],
         ['check','drive:src','drive:dst','--download','--one-way','--log-level','ERROR'],
         ['deletefile','drive:path'],
         ['serve','restic','--stdio'],
        ]
        for argv in args:
            with self.subTest(argv=argv):
                self.assertEqual(mod.inspect(argv)['status'],'DECLARED_NOT_IMPLEMENTED')
    def test_deny_unknown_or_unsafe_argv(self):
        cases={
          'EMPTY_COMMAND': [],
          'UNKNOWN_COMMAND': ['rc','core/stats'],
          'UNKNOWN_FLAG': ['lsjson','drive:a','--rc'],
          'UNDECLARED_FLAG_FORM': ['lsjson','drive:a','--config=/root/config'],
          'FLAG_VALUE_MISSING': ['lsjson','drive:a','--config'],
          'INVALID_FLAG_VALUE': ['lsjson','drive:a','--max-depth','--ignore-existing'],
          'ARGUMENT_COUNT': ['deletefile','drive:a','drive:b'],
          'UNSCOPED_OR_INVALID_PATH': ['lsjson','/data/data/private'],
          'UNSUPPORTED_STREAM': ['serve','restic'],
        }
        for expected, argv in cases.items():
            with self.subTest(expected=expected):
                self.assertEqual(mod.inspect(argv),{'status':'DENY','reason':expected})
    def test_deny_escape_and_ambiguous_locations(self):
        paths=['drive:../secret','drive:a/../../b','drive:a/./b','drive:/absolute','drive:a\\b','drive:%2e%2e/b','drive:a?query','drive:a#fragment','/root/file','./local','drive:foo\x00bar','evil@remote:a', 'rclone://bad../bad/../a','rclone://drive/a/../b']
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(mod.inspect(['lsjson',path])['status'],'DENY')
    def test_redacts_input_on_failure(self):
        sensitive='token=topsecret'
        for args in [['lsjson',sensitive],['lsjson','drive:a','--config',sensitive],['--config',sensitive]]:
            r=mod.inspect(args)
            self.assertNotIn(sensitive,json.dumps(r))
    def test_command_has_no_effects(self):
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            marker=pathlib.Path(root)/'sentinel'
            marker.write_text('KEEP')
            r=subprocess.run([sys.executable,str(SCRIPT),'--inspect-argv-json',json.dumps(['deletefile',f'drive:{marker.name}'])], capture_output=True,text=True)
            self.assertEqual(r.returncode,0) # valid syntax, no implementation
            self.assertEqual(json.loads(r.stdout)['status'],'DECLARED_NOT_IMPLEMENTED')
            self.assertEqual(marker.read_text(),'KEEP')
    def test_bad_json_denied(self):
        r=subprocess.run([sys.executable,str(SCRIPT),'--inspect-argv-json','{"secret":"a"}'],capture_output=True,text=True)
        self.assertEqual(r.returncode,2)
        self.assertEqual(json.loads(r.stdout)['status'],'DENY')
    def test_contract_has_pinned_bkx_reference(self):
        matrix=mod.load_contract()
        refs={ref for c in matrix['commands'].values() for ref in c['bkx_sources']}
        pinned=set(json.loads(mod.MANIFEST.read_text())['sha256'])
        self.assertTrue(refs<=pinned)
        self.assertIn('internal/resticops/restic.go',refs)
        self.assertTrue(all(__import__('hashlib').sha256((ROOT/'tests/fixtures/r0-consumers/bkx'/ (rel+'.fixture')).read_bytes()).hexdigest() == digest for rel,digest in json.loads(mod.MANIFEST.read_text())['sha256'].items()))

if __name__=='__main__':unittest.main()
