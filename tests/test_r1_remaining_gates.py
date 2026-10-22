import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/dev/qualification'))
import r1_remaining_gates as gates

class CrosswalkTests(unittest.TestCase):
    def r1(self):
        return {'schema':'skybind-r1-bkx-device-consolidated-v1',
                'state':'PASS_R1_BKX_AND_CHROOTCTL_NARROW_LIVE_ACCEPTANCE_ONLY',
                'remote':'GDDavys',
                'bkx_test_cases':{n:'PASS' for n in gates.R1_CASES},
                'bkx_five_positive_machine_qualified':True,
                'bkx_debug_separate_process_replay_qualified':True,
                'bkx_live_kernel_peer_attested':True,
                'bkx_negative_socket_qualified':True,
                'chrootctl_nine_security_cases_qualified':True,
                'external_provider_qualified':False,'release_qualified':False}
    def retest(self):
        return {'schema':'skybind-m2-m3-fresh-batch-v1',
                'state':'PASS_M2_M3_FRESH_NINE_LANE_AUTOMATED_RETEST_ONLY',
                'profile':'full','source_sha':'a'*40,'github_run_id':123,
                'installed_pair_verified':True,
                'm2_m3_device_retests_run':True,
                'external_provider_qualified':False,'release_qualified':False,
                'cases':{n:{'state':gates.RETEST_EXPECTED[n]} for n in gates.RETEST_CASES}}
    def test_exact_twenty_one_receipt(self):
        self.assertTrue(gates.valid_r1(self.r1(),'GDDavys'))
        for key in ('wrong_process','positive_size','revocation'):
            r=self.r1();r['bkx_test_cases'].pop(key)
            self.assertFalse(gates.valid_r1(r,'GDDavys'))
        r=self.r1();r['external_provider_qualified']=True
        self.assertFalse(gates.valid_r1(r,'GDDavys'))
    def test_full_only_and_all_cases(self):
        self.assertTrue(gates.valid_retests(self.retest()))
        r=self.retest();r['profile']='readonly'
        self.assertFalse(gates.valid_retests(r))
        r=self.retest();r['cases']['m3-copy-live']['state']='BLOCKED'
        self.assertFalse(gates.valid_retests(r))
        r=self.retest();r['cases'].pop('m3-cancel-live')
        self.assertFalse(gates.valid_retests(r))
    def test_consolidation_cannot_promote_external_or_release(self):
        r=gates.reconcile(self.r1(),self.retest(),None,'GDDavys')
        self.assertEqual(r['state'],'PASS_R1_NARROW_AND_M2_M3_FRESH_SCOPE_ONLY')
        self.assertFalse(r['external_provider_qualified'])
        self.assertFalse(r['release_qualified'])
        self.assertEqual(r['next_gate'],'OBTAIN_Q16_TWO_LANE_RAW_PROVIDER_EVIDENCE')
    def test_q16_also_cannot_promote(self):
        q={'campaign':'SB-Q16','status':'TWO_REAL_PROVIDER_LANES_VERIFIED_RAW_NOT_INDEPENDENTLY_ATTESTED',
           'independent_custody':False,'original_upstream_origin_independently_attested':False,
           'gate_evidence_generated':False,'final_seal':'NOT_ISSUED'}
        r=gates.reconcile(self.r1(),self.retest(),q,'GDDavys')
        self.assertEqual(r['next_gate'],'INDEPENDENT_G01_ORIGIN_AND_BUILDER_CUSTODY_REVIEW')
        self.assertFalse(r['external_provider_qualified'])
    def test_missing_retests_do_not_count_historic_evidence(self):
        r=gates.reconcile(self.r1(),None,None,'GDDavys')
        self.assertFalse(r['m2_m3_device_retests_run'])
        self.assertEqual(r['state'],'BLOCKED_REMAINING_QUALIFICATION_EVIDENCE_INCOMPLETE')
if __name__=='__main__':unittest.main()
