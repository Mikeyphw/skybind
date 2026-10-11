import hashlib, json, pathlib, unittest
from html.parser import HTMLParser

ROOT=pathlib.Path(__file__).resolve().parents[2]
BASE=ROOT/'tests/fixtures/webui-reference'
class HTMLControls(HTMLParser):
 def __init__(self):super().__init__();self.ids=set();self.views=set()
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if 'id' in a:self.ids.add(a['id'])
  if 'data-view' in a:self.views.add(a['data-view'])

class ContractFreeze(unittest.TestCase):
 def test_reference_bytes(self):
  m=json.loads((BASE/'manifest.json').read_text())
  for f in m['files']:
   path=BASE/'raw'/f['path']
   with self.subTest(path=f['path']):
    self.assertEqual(path.stat().st_size,f['size'])
    self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),f['sha256'])
  self.assertEqual(len(list((BASE/'raw').iterdir())),len(m['files']))

 def test_dom_retained_inventory(self):
  m=json.loads((BASE/'manifest.json').read_text());p=HTMLControls();p.feed((BASE/'raw/index.html').read_text())
  self.assertEqual(sorted(p.ids),m['dom']['ids'])
  self.assertEqual(sorted(p.views),m['dom']['data_views'])
  self.assertGreaterEqual(len(p.ids),60)
  for view in ('home','mounts','jobs','activity','runtime','remotes','doctor','logs','settings'):
   self.assertIn(view,p.views)

 def test_ui_proof_not_fabricated(self):
  m=json.loads((BASE/'manifest.json').read_text())
  self.assertEqual(m['screenshots']['status'],'NOT_CAPTURED')
  self.assertEqual(m['interaction_proofs']['status'],'NOT_EXECUTED')

 def test_57_operation_inventory(self):
  c=json.loads((ROOT/'docs/contracts/typed-operations.json').read_text())
  self.assertEqual(c['total'],len(c['operations']))
  self.assertEqual(c['total'],57)
  self.assertEqual(len({x['name'] for x in c['operations']}),57)
  for x in c['operations']:
   self.assertRegex(x['implementing_overlay'],r'^SB-O\d{2}$')
   self.assertTrue(x['webui_consumers'])

 def test_identity_and_no_new_legacy_branding(self):
  m=json.loads((ROOT/'docs/contracts/identity.json').read_text())
  i=m['identity'];self.assertEqual(i['module_id'],'skybind');self.assertEqual(i['daemon_socket'],'/data/adb/skybind/run/skybindd.sock')
  for path in [ROOT/'docs/contracts/PRODUCT_CONTRACT.md',ROOT/'docs/architecture/THREAT_MODEL.md']:
   data=path.read_text()
   for phrase in m['forbidden_new_product_names']:
    self.assertNotIn(phrase,data)

 def test_bad_reference_digest_rejected(self):
  m=json.loads((BASE/'manifest.json').read_text())
  self.assertNotEqual('0'*64, hashlib.sha256((BASE/'raw'/m['files'][0]['path']).read_bytes()).hexdigest())

if __name__=='__main__':unittest.main()
