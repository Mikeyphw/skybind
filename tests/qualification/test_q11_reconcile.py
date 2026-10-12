"""SB-Q11 tests are synthetic negative fixtures, NEVER device qualification."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

SCRIPT = Path(__file__).resolve().parents[2]/'scripts/dev/release/q11_reconcile.py'
spec = importlib.util.spec_from_file_location('sb_q11_reconcile', SCRIPT)
q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)

def h(text):
    return hashlib.sha256(text.encode()).hexdigest()

def report(phase, *, session='20261012T170516Z-a3a66e26'):
    checks = [dict(name='baseline_mount',status='PASS'),dict(name='physical_device_precheck',status='PASS')]
    obs = {}
    if phase == 'postboot':
        checks += [dict(name='postboot_recovery',status='PASS')]
        obs['postboot']={'kernel_reboot_verified':True,'installed_binary_unchanged':True,'monitor':{'elapsed_seconds':95.11}}
    if phase == 'endurance':
        checks += [dict(name='endurance',status='PASS')]
        obs['endurance']={'elapsed_seconds':3600,'samples':180}
        obs['endurance_progress']={'counts':{'boot_id_changed':0,'healthy':180,'query_errors':0,'unhealthy':0}}
    if phase == 'manual':
        checks += [dict(name=name,status='USER_REPORTED_PASS') for name in ('webui_quick_actions','download_export','secondary_app_filemanager','wifi_offline_recovery','screen_lock_wake','accessibility')]
    if phase == 'app-probe':
        checks += [dict(name='ordinary_app_read_write',status='PASS')]
        obs['ordinary_app_probe']={'app_uid':10273,'package':'org.skybind.probe','write_bytes':32,'read_bytes':32,'read_matches':True,'target_path_sha256':h('mountpoint'),'nonce_sha256':h('nonce'),'source':'installed_android_activity_private_receipt_not_run_as_simulation'}
    return dict(schema_version=1,kind='SKYBIND_SB_Q09_RAW',qualification='RAW_DEVICE_EVIDENCE_NOT_ATTESTED',session_id=session,device=dict(abi='arm64-v8a',api_level='36',device_fingerprint_sha256=h('device'),is_emulator='0'),boot_id_sha256=h('boot'),installed_binary_sha256=h('binary'),mount_identity_sha256=h('mount'),mountpoint_sha256=h('mountpoint'),baseline={'snapshot':{'observed':'RUNNING'}},checks=checks,observations=obs)

def archive(root, phase, *, r=None, corrupt=False):
    r = r or report(phase)
    p = root/f'skybind-q09-{r["session_id"]}-{phase}-20261012T235959Z-test.zip'
    payload=json.dumps(r, sort_keys=True).encode()
    summary=b'SYNTHETIC FIXTURE - NOT ATTESTATION\n'
    sums=f'{q.sha(payload)}  report.json\n{q.sha(summary)}  SUMMARY.txt\n'.encode()
    if corrupt:sums=b'0'*64+b'  report.json\n'+sums.splitlines(keepends=True)[1]
    with zipfile.ZipFile(p,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in [('report.json',payload),('SUMMARY.txt',summary),('SHA256SUMS',sums)]:z.writestr(name,data)
    return p

class TestQ11(unittest.TestCase):
    def setUp(self):
        self.dir=tempfile.TemporaryDirectory();self.addCleanup(self.dir.cleanup)
        self.path=Path(self.dir.name)
    def test_complete_raw_fixture_cannot_attest_release(self):
        for phase in q.PHASES: archive(self.path,phase)
        sid, records, bad=q.pick_session(list(self.path.glob('*.zip')),None)
        state=q.reconcile_session(records)
        self.assertEqual(state['status'],'RAW_COMPLETE_NOT_ATTESTED')
        self.assertEqual(state['checks']['manual'],'USER_REPORTED_PASS')
        self.assertFalse(bad)
    def test_app_uid_root_rejected(self):
        r=report('app-probe');r['observations']['ordinary_app_probe']['app_uid']=0
        self.assertEqual(q.reconcile_session({'baseline':{'report':report('baseline')},'app-probe':{'report':r}})['checks']['app-probe'],'UNVERIFIED')
    def test_app_wrong_target_rejected(self):
        r=report('app-probe');r['observations']['ordinary_app_probe']['target_path_sha256']=h('alias')
        self.assertEqual(q.reconcile_session({'baseline':{'report':report('baseline')},'app-probe':{'report':r}})['checks']['app-probe'],'UNVERIFIED')
    def test_app_run_as_simulation_rejected(self):
        r=report('app-probe');r['observations']['ordinary_app_probe']['source']='run_as_root_simulation'
        self.assertEqual(q.reconcile_session({'baseline':{'report':report('baseline')},'app-probe':{'report':r}})['checks']['app-probe'],'UNVERIFIED')
    def test_endurance_flap_rejected(self):
        r=report('endurance');r['observations']['endurance_progress']['counts']['unhealthy']=1
        self.assertEqual(q.reconcile_session({'baseline':{'report':report('baseline')},'endurance':{'report':r}})['checks']['endurance'],'UNVERIFIED')
    def test_postboot_without_real_boot_rejected(self):
        r=report('postboot');r['observations']['postboot']['kernel_reboot_verified']=False
        self.assertEqual(q.reconcile_session({'baseline':{'report':report('baseline')},'postboot':{'report':r}})['checks']['postboot'],'UNVERIFIED')
    def test_manual_not_independent(self):
        x=q.reconcile_session({'baseline':{'report':report('baseline')},'manual':{'report':report('manual')}})
        self.assertEqual(x['checks']['manual'],'USER_REPORTED_PASS')
    def test_fixture_hash_rejected(self):
        r=report('baseline');r['device']['device_fingerprint_sha256']='a'*64
        self.assertEqual(q.reconcile_session({'baseline':{'report':r}})['status'],'REJECTED')
    def test_emulator_rejected(self):
        r=report('baseline');r['device']['is_emulator']='1'
        self.assertEqual(q.reconcile_session({'baseline':{'report':r}})['status'],'REJECTED')
    def test_cross_report_binary_drift_rejected(self):
        r=report('postboot');r['installed_binary_sha256']=h('other-binary')
        self.assertEqual(q.reconcile_session({'baseline':{'report':report('baseline')},'postboot':{'report':r}})['status'],'REJECTED')
    def test_corrupt_checksum_rejected(self):
        p=archive(self.path,'baseline',corrupt=True)
        with self.assertRaises(q.EvidenceError):q.load_zip(p)
    def test_archive_has_exact_members(self):
        p=archive(self.path,'baseline')
        with zipfile.ZipFile(p,'a') as z:z.writestr('extraneous','evil')
        with self.assertRaises(q.EvidenceError):q.load_zip(p)
    def test_selected_session_doesnt_mix_other(self):
        archive(self.path,'baseline')
        archive(self.path,'app-probe',r=report('app-probe',session='20261012T222222Z-aaaaaaaa'))
        sid, rec, _=q.pick_session(list(self.path.glob('*.zip')),'20261012T170516Z-a3a66e26')
        self.assertNotIn('app-probe',rec)
    def test_duplicate_phase_fail_closed(self):
        archive(self.path,'baseline')
        r=report('baseline')
        x=archive(self.path,'baseline',r=r);x2=self.path/(x.name.replace('test.zip','other.zip'))
        x2.write_bytes(x.read_bytes())
        _, _, errors=q.pick_session(list(self.path.glob('*.zip')),None)
        self.assertTrue(any('duplicate phase' in e['reason'] for e in errors))
    def test_no_fake_gate_promotion_in_doc(self):
        self.assertIn('NOT_ISSUED',SCRIPT.read_text())
        self.assertIn('sb_cfs1.py',SCRIPT.read_text())
    def test_no_inputs(self):
        sid,recs,bad=q.pick_session([],None)
        self.assertIsNone(sid)
        self.assertEqual(q.reconcile_session(recs)['status'],'INCOMPLETE')

if __name__ == '__main__':unittest.main()
