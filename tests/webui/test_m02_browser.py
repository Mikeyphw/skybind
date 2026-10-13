"""M2 real-browser checks using isolated fake typed backend; no live device claims."""
import json, shutil, threading, unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from test_browser import Handler as BaseHandler, TOKEN, sync_playwright

class Handler(BaseHandler):
    metrics_calls = 0
    def do_POST(self):
        op=self.path.rsplit('/',1)[-1]
        fake={
          'config.snapshot':{'mounts':[{'name':'safegdrive','remote':'myremote:','mountpoint':'/storage/emulated/0/Rclone/Test','vfs_profile':'balanced','network_mode':'offline-allowed','enabled':True}], 'revision':1},
          'mount.status':{'mounts':[{'name':'safegdrive','observed':'RUNNING','desired':True,'pid':1234}]},
          'mount.health':{'health':[{'name':'safegdrive','state':'RUNNING','reason':'owned_fuse_mount'}]},
          'provider.remotes':{'details':[]},
          'rc.metrics':{'mount':'safegdrive','authenticated':True,'performance':{'state':'available','source':'authenticated_rclone_rc_aggregate','sampled_at_unix_ms':0,'total_speed_bytes_per_second':1048576,'transferred_bytes':2097152,'rc_errors':0,'vfs_cache_bytes':4096,'vfs_cache_files':4},'writeback':{'state':'idle','source':'authenticated_vfs_stats','uploads_queued':0,'uploads_in_progress':0,'errored_files':0}},
        }
        if op not in fake: return super().do_POST()
        if op=='rc.metrics':type(self).metrics_calls+=1
        data=dict(fake[op]);
        if op=='rc.metrics':
            import time
            data['performance']=dict(data['performance'],sampled_at_unix_ms=int(time.time()*1000))
        self.json({'schema_version':1,'request_id':'m02-test','ok':True,'result':data})

@unittest.skipIf(sync_playwright is None or not (shutil.which('chromium') or shutil.which('chromium-browser')), 'BROWSER_NOT_ATTESTED')
class Dashboard(unittest.TestCase):
    def test_on_demand_metrics_and_view_navigation(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            port=server.server_address[1];Handler.metrics_calls=0
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path=shutil.which('chromium') or shutil.which('chromium-browser'),headless=True,args=['--no-sandbox'])
                page=browser.new_page(viewport={'width':390,'height':800});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                try: page.goto(f'http://127.0.0.1:{port}/')
                except Exception as error:
                    if 'ERR_BLOCKED_BY_ADMINISTRATOR' in str(error):self.skipTest('BROWSER_NOT_ATTESTED: local navigation blocked by runner')
                    raise
                page.locator('#skybindLoginToken').fill(TOKEN)
                page.context.add_cookies([{'name':'skybind_csrf','value':'safe-token','url':f'http://127.0.0.1:{port}/'}])
                page.locator('#skybindLoginButton').click();page.locator('#skybindLogin').wait_for(state='hidden')
                page.locator('.nav-item[data-view="mounts"]').first.click()
                page.locator('.quick-mount-card').wait_for()
                self.assertEqual(Handler.metrics_calls,0,'polled RC while collapsed')
                page.locator('.perf-toggle').click();page.get_by_text('1 MiB/s',exact=False).wait_for(timeout=5000)
                self.assertGreaterEqual(Handler.metrics_calls,1)
                self.assertIn('Aggregate transfer rate',page.locator('.perf-body').inner_text())
                self.assertNotIn('/secret',page.locator('.perf-body').inner_text())
                page.locator('.perf-toggle').click()
                self.assertTrue(page.locator('.perf-body').is_hidden())
                page.locator('.nav-item[data-view="home"]').first.click()
                self.assertFalse(errors,errors)
                browser.close()
        finally:server.shutdown();server.server_close()
if __name__=='__main__':unittest.main()
