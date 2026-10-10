import json, pathlib, re, unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]
CANON=ROOT/'docs/contracts/typed-operations.json'
EMBED=ROOT/'internal/control/operations.json'
WEBUI=ROOT/'tests/fixtures/webui-reference/raw/app.js'
# Excluded behavior is not copied into the new product. No UI controls are
# removed here; the approved surgical edit happens in the later UI overlays.
EXCLUDED={'migration.status','migration.inspect','migration.preview','migration.apply',
'migration.finalize.preview','migration.finalize','migration.rollback','migration.recover',
'provider.crypt.migrations','provider.crypt.migrate.preview','provider.crypt.migrate',
'provider.crypt.cleanup.preview','provider.crypt.cleanup'}
class CatalogCrosswalk(unittest.TestCase):
 def test_exact_canonical_copy(self):
  self.assertEqual(EMBED.read_bytes(),CANON.read_bytes())
  c=json.loads(EMBED.read_text());self.assertEqual(c['total'],57)
  self.assertEqual(len({v['name'] for v in c['operations']}),57)
 def test_original_ui_required_operations_in_scope(self):
  js=WEBUI.read_text();body=js.split('function requiredOperations(caps) {',1)[1].split('async function ensureConnected',1)[0]
  array=body.split('const required = [',1)[1].split('];',1)[0]
  original=set(re.findall(r"'([a-z][a-z0-9_.]+)'",array))
  canonical={x['name'] for x in json.loads(CANON.read_text())['operations']}
  self.assertTrue(EXCLUDED <= original)
  self.assertFalse((original-EXCLUDED)-canonical, 'retained source WebUI requirement missing from catalog')
  self.assertFalse(EXCLUDED & canonical, 'excluded behaviors leaked into the new API')
 def test_protocol_source_has_no_generic_execution(self):
  s=(ROOT/'internal/daemon/wiring.go').read_text()
  for symbol in ('shell.exec','runtime.select','migration.apply'):
   self.assertNotIn(symbol,s)
if __name__=='__main__':unittest.main()
