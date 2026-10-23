"""Personal release authority: evidence truth and owner consent regression."""
from pathlib import Path
import importlib.util
import hashlib
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
SCRIPT=ROOT/'scripts/dev/qualification/personal_policy.py'
spec=importlib.util.spec_from_file_location('personal_policy',SCRIPT)
p=importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

class PersonalPolicyTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.addCleanup(self.tmp.cleanup)
  self.folder=Path(self.tmp.name)/'state'
  self.evdir=Path(self.tmp.name)/'receipts';self.evdir.mkdir()
  self.s={'commit':'a'*40,'lock_sha256':'f'*64,'newfuture_asset_sha256':'1'*64,
          'bclone_commit':'b'*40,'source_hashes':{'control':'c'*64}}
  self.product_patch=patch.object(p,'product_compatible',return_value=True)
  self.product_patch.start();self.addCleanup(self.product_patch.stop)
  self.fixtures=self.make_fixtures()
  self.paths={}
  for k,v in self.fixtures.items():
   self.paths[k]=self.evdir/(k+'.json')
   self.paths[k].write_text(json.dumps(v,sort_keys=True))
 def make_fixtures(self):
  packages={'bclone':'2'*64,'newfuture':'3'*64}
  lane={'job_id':8,'official_asset_sha256':'1'*64,
        'source_build_binary_sha256':'4'*64,'provider_packages':packages}
  q16={'campaign':'SB-Q16','status':'TWO_REAL_PROVIDER_LANES_VERIFIED_RAW_NOT_INDEPENDENTLY_ATTESTED',
       'source_lock_sha256':'f'*64,'run':{'commit':p.BASE_SHA},
       'lanes':{'A':lane,'B':{**lane,'job_id':9}},
       'comparison':{'status':'BYTE_IDENTICAL_UNATTESTED','source_commit':'b'*40,
                     'bclone.zip_sha256':'2'*64,'newfuture.zip_sha256':'3'*64}}
  q17={'campaign':'SB-Q17','status':'TWO_FRESH_RAW_NEGATIVE_RUNS_VERIFIED_NOT_INDEPENDENT',
       'case_count':10,'run_ids':['1'*32,'2'*32],'source_commit':p.BASE_SHA,
       'source_hashes':self.s['source_hashes']}
  r1={'schema':'skybind-r1-bkx-device-consolidated-v1',
      'state':'PASS_R1_BKX_AND_CHROOTCTL_NARROW_LIVE_ACCEPTANCE_ONLY',
      'remote':'GDDavys',
      'bkx_test_cases':{n:'PASS' for n in (
          'no_token','positive_capabilities','positive_version','positive_remotes','positive_list','positive_size',
          'wrong_operation','wrong_remote','wrong_path','wrong_process','revocation','expiry')},
      **{k:True for k in ('bkx_five_positive_machine_qualified',
          'bkx_debug_separate_process_replay_qualified','bkx_live_kernel_peer_attested',
          'bkx_negative_socket_qualified','chrootctl_nine_security_cases_qualified')}}
  expected={'live':'PASS_M2_L1_LIVE_READ_BROWSE_REBIND','ui-live':'PASS_M2_L2_LIVE_UI_READONLY_RECOVERY',
       'negative-live':'PASS_M2_L3_READONLY_NEGATIVE_BOUNDARIES',
       'transport-live':'PASS_M2_L3_APP_OWNED_TRANSPORT_RECOVERY',
       'm3-preview-live':'PASS_M3_REAL_DAEMON_PREVIEW_ONLY',
       'm3-execute-live':'PASS_M3_DISPOSABLE_CHECK_COMPLETION',
       'm3-cancel-live':'PASS_M3_DISPOSABLE_OWNED_CANCEL',
       'm3-copy-live':'PASS_M3_DISPOSABLE_COPY_RECONCILED',
       'm2-process-live':'PASS_M2_L3_APP_PROCESS_COLD_LAUNCH'}
  m2={'schema':'skybind-m2-m3-fresh-batch-v1','state':'PASS_M2_M3_FRESH_NINE_LANE_AUTOMATED_RETEST_ONLY',
      'github_run_id':39849958085,'source_sha':p.BASE_SHA,
      'installed_pair_verified':True,'m2_m3_device_retests_run':True,
      'cases':{k:{'state':v} for k,v in expected.items()},
      'copy_preflight':{'source_verified':True,'expected_content_sha256':'6'*64},
      'copy_integrity':{'destination_verified':True,'sentinel_preserved':True,
                        'expected_content_sha256':'6'*64}}
  return {'q16':q16,'q17':q17,'r1':r1,'m2m3':m2}
 def setup_evidence(self):
  with patch.object(p,'source',return_value=self.s):
   out=p.configure(ROOT,self.folder,self.paths)
   self.assertEqual(out['status'],'PERSONAL_EVIDENCE_CONFIGURED')
 def test_complete_first_party_acceptance_stays_pending_owner(self):
  self.setup_evidence()
  with patch.object(p,'source',return_value=self.s):
   r=p.assess(ROOT,self.folder)
  self.assertEqual(r['status'],'PERSONAL_RELEASE_PENDING')
  self.assertFalse(r['independent_certification_claimed'])
  for gate in ('SB-G01','SB-G02','SB-G05','SB-G06'):
   self.assertEqual(r['gate_checks'][gate]['status'],'PERSONAL_EVIDENCE_PASS')
 def test_evidence_tamper_denied(self):
  self.setup_evidence()
  self.paths['q17'].write_text('{"modified":true}')
  with patch.object(p,'source',return_value=self.s):r=p.assess(ROOT,self.folder)
  self.assertIn('EVIDENCE_CHANGED_Q17',r['reasons'])
  self.assertNotEqual(r['gate_checks']['SB-G02']['status'],'PERSONAL_EVIDENCE_PASS')
 def test_missing_ui_or_device_ack_denied(self):
  self.setup_evidence()
  with patch.object(p,'source',return_value=self.s):
   for ui,device in ((False,True),(True,False)):
    with self.assertRaisesRegex(p.Rejected,'EXPLICIT_UI_AND_DEVICE_REVIEW_REQUIRED'):
     p.approve(ROOT,self.folder,Path('missing.zip'),'kernelsu',ui,device,True)
   self.assertFalse((self.folder/'owner-approval.json').exists())
 def test_scope_specific_owner_approval_and_candidate_drift(self):
  self.setup_evidence()
  candidate=self.evdir/'Skybind-bclone-PERSONAL.zip';candidate.write_bytes(b'x'*300)
  approved={'path':str(candidate),'sha256':p.digest(candidate),'provider':'bclone','format_verified':True}
  with patch.object(p,'source',return_value=self.s),patch.object(p,'candidate_info',return_value=approved):
   r=p.approve(ROOT,self.folder,candidate,'kernelsu',True,True,True)
   self.assertEqual(r['status'],'PERSONAL_RELEASE_APPROVED')
   self.assertEqual(r['gate_checks']['SB-G08']['status'],'PERSONAL_OWNER_ACCEPTED')
   self.assertTrue(r['untested_managers_not_qualified'])
  altered=dict(self.s,commit='d'*40)
  with patch.object(p,'source',return_value=altered),patch.object(p,'candidate_info',return_value=approved):
   r=p.assess(ROOT,self.folder)
   self.assertEqual(r['status'],'PERSONAL_RELEASE_PENDING')
   self.assertTrue(any('OWNER_SOURCE_DRIFT' in x for x in r['reasons']))
 def test_fake_copy_receipt_denied(self):
  self.fixtures['m2m3']['copy_integrity']['sentinel_preserved']=False
  self.paths['m2m3'].write_text(json.dumps(self.fixtures['m2m3']))
  with patch.object(p,'source',return_value=self.s):
   with self.assertRaisesRegex(p.Rejected,'M2M3_EVIDENCE_INVALID'):
    p.configure(ROOT,self.folder,self.paths)
 def test_unverified_candidate_rejected(self):
  fake=self.evdir/'Skybind-bclone-PERSONAL.zip';fake.write_bytes(b'garbage')
  with self.assertRaises(p.Rejected):p.candidate_info(self.evdir/'other.zip')
  with self.assertRaises(Exception):p.candidate_info(fake)
 def test_private_state_refuses_overwrite(self):
  self.setup_evidence()
  with patch.object(p,'source',return_value=self.s):
   with self.assertRaisesRegex(p.Rejected,'STATE_FILE_ALREADY_EXISTS'):
    p.configure(ROOT,self.folder,self.paths)
if __name__=='__main__':unittest.main()
