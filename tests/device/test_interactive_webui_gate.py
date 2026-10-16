"""Source-specific negative acceptance contract for V9, not physical Android tests."""
import datetime as dt
import importlib.util
import pathlib
import sys
import unittest
R=pathlib.Path(__file__).resolve().parents[2]
D=R/'scripts/dev/device'
sys.path.insert(0,str(D))
spec=importlib.util.spec_from_file_location('interactive_webui_gate',D/'interactive_webui_gate.py')
v9=importlib.util.module_from_spec(spec)
spec.loader.exec_module(v9)

class V9Contract(unittest.TestCase):
    def claim(self,obs,owned=None,ui=None,jobs=None,events=None,fg=True,asset=True):
        return {x['test']:x for x in v9.claim_result(obs,foreground=fg,asset_matches=asset,
           ui=ui or {},jobs=jobs or {},ownership=owned,events=events,
           host='vtebo2.rezdpneqo9vt.d2wjkhzv77ptrycwv')}
    def test_receipt_requires_version(self):
        with self.assertRaises(v9.GateError):v9.check_receipt({'kind':'untrusted','schema_version':1})
    def test_receipt_accepts_sanitized_observations(self):
        sample={'schema_version':1,'kind':v9.KIND,
          'recorded_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
          'document_id':'20261016-valid','observations':{'navigation_preview':{'status':'BLOCKED'}}}
        self.assertEqual(v9.check_receipt(sample)['navigation_preview']['status'],'BLOCKED')
        sample['observations']['navigation_preview']['status']='PASSED'
        with self.assertRaises(v9.GateError):v9.check_receipt(sample)
    def test_stale_receipt_refused(self):
        with self.assertRaises(v9.GateError):v9.stamp_check('2022-01-01T00:00:00Z')
    def test_missing_ui_identity_remains_blocked(self):
        claim={'navigation_preview':{'status':'PASS','preview_is_readonly_kind':True,
                'trusted_navigation':True,'trusted_preview':True,'confirm_enabled':True}}
        self.assertEqual(self.claim(claim)['navigation_preview']['status'],'BLOCKED')
    def test_readonly_preview_attested_ui_can_pass(self):
        claim={'navigation_preview':{'status':'PASS','preview_is_readonly_kind':True,
                'trusted_navigation':True,'trusted_preview':True,'confirm_enabled':True}}
        ui={'host_package_present':True,'skybind_page':True,'preview_control':True}
        self.assertEqual(self.claim(claim,ui=ui)['navigation_preview']['status'],'PASS')
    def test_copy_preview_not_promoted(self):
        claim={'navigation_preview':{'status':'PASS','preview_is_readonly_kind':False,
                'trusted_navigation':True,'trusted_preview':True,'confirm_enabled':True}}
        ui={'host_package_present':True,'skybind_page':True,'preview_control':True}
        self.assertEqual(self.claim(claim,ui=ui)['navigation_preview']['status'],'BLOCKED')
    def test_reopen_never_implies_close(self):
        id='a'*32
        obs={'reconnection':{'status':'PASS','run_id':id}}
        rows=self.claim(obs,owned={'baseline_run_ids':[]},jobs={id:{'state':'COMPLETED'}},events={'gap':False})
        self.assertEqual(rows['reconnection']['status'],'BLOCKED')
        self.assertEqual(rows['reconnection']['evidence']['document_reopen_and_authoritative_job'],'OBSERVED')
    def test_cancellation_unowned_refused(self):
        id='a'*32
        rows=self.claim({'owned_cancellation':{'status':'PASS','run_id':id,'trusted_cancel':True}},
                         jobs={id:{'state':'CANCELLED'}},events={'cancelled':True})
        self.assertEqual(rows['owned_cancellation']['status'],'BLOCKED')
    def test_owned_cancellation_requires_hashes_and_new_id(self):
        id='a'*32; a='1'*64;b='2'*64
        claim={'navigation_preview':{'status':'BLOCKED','trusted_copy_launch':{'trusted_confirm':True,'kind':'copy','source_endpoint_sha256':a,'destination_endpoint_sha256':b}},
               'owned_cancellation':{'status':'BLOCKED','run_id':id,'trusted_cancel':True}}
        owned={'source_sha256':a,'destination_sha256':b,'baseline_run_ids':[]}
        self.assertEqual(self.claim(claim,owned=owned,jobs={id:{'state':'CANCELLED'}},events={'cancelled':True})['owned_cancellation']['status'],'PASS')
        owned['baseline_run_ids']=[id]
        self.assertEqual(self.claim(claim,owned=owned,jobs={id:{'state':'CANCELLED'}},events={'cancelled':True})['owned_cancellation']['status'],'BLOCKED')
    def test_synthetic_fault_never_claims_real_outage(self):
        claim={'read_only_bridge_recovery':{'status':'PASS','one_shot_fault_consumed':True,
          'ui_recovered':True,'mutations_dispatched_during_test':0,'replay_cursor_monotonic':True}}
        case=self.claim(claim)['read_only_bridge_recovery']
        self.assertEqual(case['status'],'PASS')
        self.assertIn('synthetic',case['evidence']['scope'])
    def test_mutation_during_fault_blocks(self):
        claim={'read_only_bridge_recovery':{'status':'PASS','one_shot_fault_consumed':True,
          'ui_recovered':True,'mutations_dispatched_during_test':1,'replay_cursor_monotonic':True}}
        self.assertEqual(self.claim(claim)['read_only_bridge_recovery']['status'],'BLOCKED')
    def test_unmatched_installed_asset_blocks_all(self):
        claim={k:{'status':'PASS'} for k in v9.NAMES}
        rows=self.claim(claim,asset=False)
        self.assertTrue(all(x['status']=='BLOCKED' for x in rows.values()))
    def test_no_device_cancellation_code(self):
        source=(D/'interactive_webui_gate.py').read_text()
        self.assertNotIn("rpc.call('operation.cancel'",source)
        self.assertNotIn('subprocess.run(["reboot"',source)
    def test_devtool_wrapper_present(self):
        cfg=(R/'.devtool.toml').read_text()
        for name in ('api-webui-interactive-prep','api-webui-interactive-gate'):
            self.assertIn('[wrapper.commands.'+name+']',cfg)
    def test_xml_sanitizes_fields(self):
        data='''<?xml version="1.0"?><hierarchy><node package="vtebo2.rezdpneqo9vt.d2wjkhzv77ptrycwv" text="Skybind"/><node package="vtebo2.rezdpneqo9vt.d2wjkhzv77ptrycwv" text="Preview transfer policy" /></hierarchy>'''
        result=v9.attested_ui_structure('vtebo2.rezdpneqo9vt.d2wjkhzv77ptrycwv',command=lambda *a,**k:data)
        self.assertTrue(result['preview_control'])
        self.assertNotIn('raw',result)
if __name__=='__main__':unittest.main()
