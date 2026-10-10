import hashlib,json,pathlib,re,unittest,html.parser
ROOT=pathlib.Path(__file__).resolve().parents[2]
BASE=ROOT/'tests/fixtures/webui-reference/raw'
UI=ROOT/'module/webroot'
class Tags(html.parser.HTMLParser):
 def __init__(self):super().__init__();self.ids=set();self.views=set()
 def handle_starttag(self,t,attrs):
  a=dict(attrs)
  if 'id' in a:self.ids.add(a['id'])
  if 'data-view' in a:self.views.add(a['data-view'])
class Parity(unittest.TestCase):
 def test_reference_untouched(self):
  m=json.loads((BASE.parent/'manifest.json').read_text())
  for item in m['files']:
   p=BASE/item['path'];self.assertTrue(p.is_file())
   self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),item['sha256'])
 def test_retained_style_and_icon(self):
  self.assertEqual((UI/'icon.png').read_bytes(),(BASE/'icon.png').read_bytes())
  self.assertTrue((UI/'style.css').read_bytes().startswith((BASE/'style.css').read_bytes()))
 def test_navigation_structure_and_mobile_contract(self):
  a=Tags();b=Tags();a.feed((BASE/'index.html').read_text());b.feed((UI/'index.html').read_text())
  for view in ('home','mounts','jobs','activity','more','runtime','remotes','doctor','logs','settings'):
   self.assertIn(view,b.views)
  self.assertEqual(a.views,b.views)
  excluded={'legacyActivityToggle','legacyActivityCount','migrateCurrentRemoteButton','remoteMigrateCrypt',
   'cryptMigrationBackdrop','cryptMigrationTitle','closeCryptMigrationButton',
   'cryptMigrationForm','crypt-migration-source','crypt-migration-destination-remote',
   'crypt-migration-destination-path','cryptMigrationError','cryptMigrationPreview',
   'cleanupCryptMigrationButton','previewCryptMigrationButton','runCryptMigrationButton'}
  self.assertEqual(a.ids-excluded,b.ids-set(('skybindLogin','skybindLoginForm','skybindLoginHeading','skybindLoginToken','skybindLoginError','skybindLoginButton')))
  html=(UI/'index.html').read_text()
  for entry in ('viewport-fit=cover','class="desktop-nav"','id="view-home"','id="view-mounts"','id="editorBackdrop"','id="jobBackdrop"'):
   self.assertIn(entry,html)
 def test_identity_and_exclusion(self):
  for n in ('index.html','app.js','bridge.js','model.js','config.json','platform.json'):
   content=(UI/n).read_text()
   for forbidden in ('Rclone Nexus','rclone_nexus','rnexus_csrf','racctl'):
    self.assertNotIn(forbidden,content, (n,forbidden))
  html=(UI/'index.html').read_text()
  for forbidden in ('cryptMigrationBackdrop','remoteMigrateCrypt','legacyActivityToggle'):
   self.assertNotIn(forbidden,html)
 def test_typed_transport_security(self):
  bridge=(UI/'bridge.js').read_text()
  for required in ('/data/adb/modules/skybind/system/bin/skybind','X-Skybind-CSRF','X-Skybind-Request-ID','/auth/bootstrap','normalizeResponse','newRequestId'):
   self.assertIn(required,bridge)
  self.assertNotIn('localStorage',bridge)
  self.assertNotIn('eval(',bridge)
 def test_auth_shell_and_release_truth(self):
  html=(UI/'index.html').read_text();self.assertIn('id="skybindLoginForm"',html)
  index=json.loads((ROOT/'docs/roadmap/SKYBIND_DEVTOOL_OVERLAY_INDEX.json').read_text())
  statuses=[x['status'] for x in index['artifact_sequence']]
  self.assertEqual(statuses[:5],['SOURCE_IMPLEMENTED_NOT_PROMOTED']*5)
  self.assertIn(statuses[5],('PLANNED','SOURCE_IMPLEMENTED_NOT_PROMOTED'))
  self.assertEqual(statuses[6:],['SOURCE_IMPLEMENTED_NOT_PROMOTED','PLANNED'])
  self.assertEqual(index['starting_position']['gate_qualification'],{'SB-G01':'BLOCKED','SB-G02':'BLOCKED'})
if __name__=='__main__':unittest.main()
