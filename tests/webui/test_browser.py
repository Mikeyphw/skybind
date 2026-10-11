"""Optional Chromium interaction evidence; runs when Playwright+Chromium are installed.
Missing tooling is reported as NOT_ATTESTED, never as visual proof.
"""
import http.server, socketserver, threading, json, pathlib, unittest, shutil
ROOT=pathlib.Path(__file__).resolve().parents[2]
ASSETS=ROOT/'module/webroot'
TOKEN='a'*64
try:
 from playwright.sync_api import sync_playwright
except ImportError:
 sync_playwright=None

class Handler(http.server.SimpleHTTPRequestHandler):
 def __init__(self,*a,**kw):super().__init__(*a,directory=str(ASSETS),**kw)
 def log_message(self,*x):pass
 def do_GET(self):
  if self.path=='/api/v1/transport':return self.json({'schema_version':1,'transport':'standalone','typed_backend':True})
  if self.path=='/api/v1/capabilities':
   if not self.auth():return self.send_error(401)
   ops=json.loads((ROOT/'internal/control/operations.json').read_text())['operations']
   return self.json({'schema_version':1,'protocol':{'min':1,'max':1},'operations':ops})
  return super().do_GET()
 def auth(self):return 'skybind_session=ok' in self.headers.get('Cookie','')
 def json(self,value,status=200):
  b=json.dumps(value).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 def do_POST(self):
  n=int(self.headers.get('Content-Length',0));data=json.loads(self.rfile.read(n) or b'{}')
  if self.path=='/auth/bootstrap':
   if data.get('token') != TOKEN:return self.send_error(403)
   self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Set-Cookie','skybind_session=ok; Path=/; SameSite=Strict');self.send_header('Content-Length','2');self.end_headers();self.wfile.write(b'{}');return
  if not self.auth() or not self.headers.get('X-Skybind-CSRF'):return self.send_error(403)
  op=self.path.rsplit('/',1)[-1]
  results={
   'ui.settings':{'settings':{'default_view':'home','refresh_seconds':10,'log_limit':100}},
   'runtime.status':{'operational':False,'mode':'static','source':'bundled'},
   'provider.status':{'fuse_helper_ready':False,'fuse_device_ready':False},
   'mount.status':{'mounts':[]},'platform.status':{'root_manager':'unknown'},
   'operation.list':{'operations':[]},'policy.status':{'policies':[]},
   'config.snapshot':{'mounts':[],'revision':0},'mount.health':{'health':[]},
   'jobs.snapshot':{'jobs':[],'revision':0},'jobs.status':{'jobs':[]},
   'provider.remotes':{'remotes':[],'details':[]},'diagnostics.logs':{'records':[]},
   'provider.crypt.password.status':{'configured':False},
   'provider.crypt.recovery.status':{'password_configured':False},
   'vfs.profiles':{'profiles':[]},'doctor.report':{'checks':[]},
   'cache.status':{'caches':[]},
  }
  obj={'schema_version':1,'request_id':self.headers.get('X-Skybind-Request-ID','test-1'),'ok':True,'result':results.get(op,{})}
  return self.json(obj)

class UI(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);cls.port=cls.server.server_address[1]
  cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
 @classmethod
 def tearDownClass(cls):cls.server.shutdown();cls.server.server_close()
 @unittest.skipIf(sync_playwright is None or not (shutil.which('chromium') or shutil.which('chromium-browser')), 'BROWSER_NOT_ATTESTED: Playwright/Chromium unavailable')
 def test_browser_auth_navigation_and_modal(self):
  with sync_playwright() as p:
   browser=p.chromium.launch(executable_path=shutil.which('chromium') or shutil.which('chromium-browser'),headless=True,args=['--no-sandbox'])
   page=browser.new_page(viewport={'width':390,'height':844},device_scale_factor=1)
   errors=[];page.on('pageerror',lambda exc:errors.append(str(exc)))
   try:
    page.goto(f'http://127.0.0.1:{self.port}/',wait_until='domcontentloaded')
   except Exception as error:
    if 'ERR_BLOCKED_BY_ADMINISTRATOR' in str(error):
     self.skipTest('BROWSER_NOT_ATTESTED: browser navigation blocked by runner policy')
    raise
   page.locator('#skybindLogin').wait_for(state='visible',timeout=10000)
   self.assertEqual(page.locator('#skybindLoginForm').count(),1)
   # Mock authenticated CSRF cookie from the standalone token exchange.
   page.locator('#skybindLoginToken').fill(TOKEN)
   page.context.add_cookies([{'name':'skybind_csrf','value':'safe-token','url':f'http://127.0.0.1:{self.port}/'}])
   page.locator('#skybindLoginButton').click()
   page.locator('#skybindLogin').wait_for(state='hidden',timeout=10000)
   page.locator('#view-home').wait_for(state='visible',timeout=10000)
   self.assertIn('Skybind',page.title())
   page.locator('.nav-item[data-view="mounts"]').first.click()
   page.locator('#view-mounts').wait_for(state='visible')
   page.locator('#addMountButton').click()
   self.assertFalse(page.locator('#editorBackdrop').is_hidden())
   page.locator('#closeEditorButton').click()
   # closeEditor sometimes opens discard confirm, both are expected UX transitions.
   self.assertTrue(page.locator('#editorBackdrop').is_hidden() or not page.locator('#discardBackdrop').is_hidden())
   self.assertFalse(errors,'browser exceptions: '+repr(errors))
   browser.close()
