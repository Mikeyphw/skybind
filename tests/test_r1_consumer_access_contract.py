"""R1 policy source-contract and narrow device evidence reconciliation negatives."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('m3_evidence',ROOT/'scripts/dev/android/m3_evidence_reconcile.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class M3Evidence(unittest.TestCase):
    def test_independently_versioned_scopes_without_release_promotion(self):
        with tempfile.TemporaryDirectory() as d:
            dest=Path(d); native=dest/'native';native.mkdir()
            receipts=[]
            for i,(lane,(flag,state,scope)) in enumerate(m.SCOPES.items(),start=1):
                base={'schema':'skybind-m2-live-v1','source_sha':format(i,'040x'),
                      'github_run_id':i+1000,'artifact_id':i+9000,
                      'state':state,'qualified_scope':scope,flag:True,
                      'installed_pair_verified':True,'signing_verified':True,
                      'release_qualified':False,'device_qualified':False}
                if lane=='m3-copy-live':
                    pre={'count':128,'source_verified':True,'expected_content_sha256':'f'*64}
                    post={**pre,'destination_verified':True,'sentinel_preserved':True}
                    base.update(copy_preflight=pre,copy_integrity=post)
                p=native/f'native{i}.json';p.write_text(json.dumps(base))
                summary={key:base[key] for key in ('source_sha','github_run_id','artifact_id','installed_pair_verified')}
                summary.update(status='PASS_CI_PAIR_AND_SELECTED_LANES',selected_lanes=[lane],
                               tests={lane:{'state':state,'qualified_scope':scope,'receipt':str(p)}},**{flag:True})
                q=dest/f'summary{i}.json';q.write_text(json.dumps(summary));receipts.append(q)
            r=m.reconcile(receipts,native)
            self.assertEqual(r['status'],'PASS_FOUR_INDEPENDENT_M3_SCOPES')
            self.assertFalse(r['release_qualified'])
            self.assertFalse(r['whole_m3_qualified'])
            self.assertEqual(len({x['source_sha'] for x in r['qualified_scopes'].values()}),4)
            only=m.reconcile(receipts[:1],native)
            self.assertEqual(only['status'],'BLOCKED_M3_EVIDENCE_INCOMPLETE')
            self.assertEqual(len(only['missing_scopes']),3)
            # Tamper native signer, not just summary, and deny that lane.
            b=json.loads((native/'native4.json').read_text());b['signing_verified']=False
            (native/'native4.json').write_text(json.dumps(b))
            r=m.reconcile(receipts,native)
            self.assertIn('m3-copy-live',r['missing_scopes'])

    def test_gateway_contract_does_not_claim_transport(self):
        abi=json.loads((ROOT/'docs/contracts/rclone-compat/SKYBIND_CONSUMER_ABI_V1.json').read_text())
        self.assertEqual(abi['available_external_capabilities'],[])
        self.assertEqual(abi['external_transport_status'],'NOT_IMPLEMENTED')
        source=(ROOT/'internal/brokeridentity/root.go').read_text()
        self.assertIn('ModuleSealSHA256',source)
        self.assertIn('ModuleAttestor',source)
        self.assertNotIn('net.Listen(',source)
        self.assertNotIn('exec.Command(',source)

if __name__=='__main__':unittest.main()
