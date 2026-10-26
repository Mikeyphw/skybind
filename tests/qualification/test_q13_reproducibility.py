"""SB-Q13 source-bound tests: actual sha/receipts and fail-closed comparisons."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[2] / 'scripts/dev/release/q13_reproducibility.py'
spec = importlib.util.spec_from_file_location('q13_tested', SOURCE)
q13 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q13)

HASH = 'a' * 64
B_HASH = 'b' * 64
C_HASH = 'c' * 64

def candidate(prov, sha, daemon=HASH, helper=B_HASH, runtime=C_HASH):
    return {'status': 'VALID_UNQUALIFIED_CANDIDATE', 'file': f'skybind-{prov}-CANDIDATE-UNQUALIFIED.zip',
            'sha256': sha, 'provider': prov, 'members': {'system/bin/skybind': daemon,
                                     'system/vendor/bin/fusermount3': helper,
                                     'system/bin/rclone': HASH,
                                     'system/bin/skybind-rclone': HASH,
                                     'system/bin/skybind-rclone-engine': runtime,
                                     'runtime.provenance.json': HASH if prov=='newfuture' else B_HASH}}


def lane(name, a=None, b=None):
    return {'lane': name, 'providers': {'newfuture': a or {'status': 'MISSING'},
                                      'bclone': b or {'status': 'MISSING'}}}

class Q13Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    def fixture(self, providers=('newfuture', 'bclone'), tamper=None):
        lane_dir = self.base / f'lane{len(list(self.base.iterdir()))}'
        lane_dir.mkdir()
        files = {}
        receipt = {'schema_version': 1, 'build_kind': 'LOCAL_DEVELOPMENT_UNQUALIFIED',
                   'final_seal': 'NOT_ISSUED', 'independent_attestation': False,
                   'candidates': {}, 'q12_source_build': None}
        for p in providers:
            name = f'skybind-{p}-CANDIDATE-UNQUALIFIED.zip'
            f = lane_dir / name
            f.write_bytes((p + ' UNQUALIFIED').encode())
            s = q13.sha(f)
            receipt['candidates'][p] = {'file': name, 'sha256': s}
            files[p] = candidate(p, s, runtime=HASH if p=='newfuture' else B_HASH)
        if tamper:
            receipt.update(tamper)
        (lane_dir / 'candidate-evidence.json').write_text(json.dumps(receipt))
        return lane_dir, files

    def test_same_provider_identical(self):
        a = lane('a', candidate('newfuture', HASH), candidate('bclone', B_HASH))
        b = lane('b', candidate('newfuture', HASH), candidate('bclone', B_HASH))
        self.assertTrue(all(x['status']=='BYTE_IDENTICAL_UNATTESTED' for x in q13.same_provider(a,b).values()))

    def test_changed_single_byte_fails(self):
        a = lane('a', candidate('newfuture', HASH), candidate('bclone', B_HASH))
        b = lane('b', candidate('newfuture', C_HASH), candidate('bclone', B_HASH))
        self.assertEqual(q13.same_provider(a,b)['newfuture']['status'], 'DIFFERENT_BYTES')
        self.assertEqual(q13.same_provider(a,b)['bclone']['status'], 'BYTE_IDENTICAL_UNATTESTED')

    def test_runtime_mismatch_expected_cross_provider(self):
        a=lane('a',candidate('newfuture', HASH, runtime=HASH),candidate('bclone', B_HASH, runtime=B_HASH))
        cross=q13.cross_provider(a)
        self.assertEqual(cross['status'],'SHARED_PAYLOAD_MATCH_UNATTESTED')
        self.assertTrue(cross['provider_runtime_distinct'])

    def test_helper_mismatch_not_ignored(self):
        a=lane('a',candidate('newfuture', HASH, helper=HASH),candidate('bclone', B_HASH, helper=B_HASH))
        self.assertEqual(q13.cross_provider(a)['status'],'SHARED_PAYLOAD_MISMATCH')

    def test_missing_provider_not_both(self):
        self.assertEqual(q13.cross_provider(lane('a',candidate('newfuture', HASH)))['status'],'BOTH_PROVIDERS_REQUIRED')

    def test_valid_lane_reads_authoritative_q12_verifier(self):
        folder, files = self.fixture()
        with patch.object(q13.q12, 'inspect_candidate', side_effect=lambda p: files[p.name.split('-')[1]]):
            result=q13.inspect_lane(folder,self.base)
        self.assertEqual(result['status'],'VALID_UNQUALIFIED_LANE')
        self.assertEqual(result['source_receipt'],'NOT_RECORDED')
        self.assertFalse(result['independent_build'])

    def test_tampered_receipt_rejected(self):
        folder, files = self.fixture()
        with patch.object(q13.q12, 'inspect_candidate', side_effect=lambda p: files[p.name.split('-')[1]]):
            (folder / 'candidate-evidence.json').write_text(json.dumps({'build_kind':'SIGNED_RELEASE','final_seal':'ISSUED','candidates':{}}))
            with self.assertRaises(ValueError):q13.inspect_lane(folder,self.base)

    def test_wrong_hash_rejected(self):
        folder, files=self.fixture()
        file=folder/'candidate-evidence.json'
        obj=json.loads(file.read_text()); obj['candidates']['bclone']['sha256']=HASH
        file.write_text(json.dumps(obj))
        with patch.object(q13.q12,'inspect_candidate',side_effect=lambda p: files[p.name.split('-')[1]]):
            with self.assertRaises(ValueError):q13.inspect_lane(folder,self.base)

    def test_symlink_lane_rejected(self):
        folder,_=self.fixture()
        link=self.base/'linked'
        link.symlink_to(folder,target_is_directory=True)
        with self.assertRaises(ValueError):q13.safe_lane(link)

    def test_symlink_receipt_rejected(self):
        folder,files=self.fixture()
        original=folder/'candidate-evidence.json'
        moved=folder/'hidden.json'
        original.rename(moved);original.symlink_to(moved)
        with self.assertRaises(ValueError):q13.inspect_lane(folder,self.base)

    def test_missing_and_ambiguous_auto_selection(self):
        self.assertEqual(q13.local_candidates(self.base)[1], 'NO_LOCAL_CANDIDATES')
        folder,files=self.fixture();folder2,files2=self.fixture()
        dist=self.base/'dist/local-candidates';dist.mkdir(parents=True)
        (dist/'candidate-1').symlink_to(folder,target_is_directory=True)
        self.assertEqual(q13.local_candidates(self.base)[1], 'NO_LOCAL_CANDIDATES')

    def test_no_lanes_no_gate_promotion(self):
        with patch.object(q13,'gate_diagnostics',return_value=({f'SB-G{i:02}':{'status':'BLOCKED','reasons':['MISSING']} for i in range(1,9)}, {'status':'BLOCKED','seal':'NOT_ISSUED','reasons':[]})),patch.object(q13.q12,'source_identity',return_value={'worktree_clean':True}):
            result=q13.evaluate(self.base,source_only=True)
        self.assertEqual(result['final_seal'],'NOT_ISSUED')
        self.assertFalse(result['independent_attestation'])
        self.assertEqual(len(result['gate_blockers']),8)

    def test_repeat_lane_identity_rejected(self):
        folder,_=self.fixture()
        with patch.object(q13,'gate_diagnostics',return_value=({},{})),patch.object(q13.q12,'source_identity',return_value={}):
            res=q13.evaluate(self.base,lane_a=folder,lane_b=folder,source_only=True)
        self.assertTrue(any('LANE_B_INVALID' in issue for issue in res['issues']))

    def test_markdown_does_not_promote_seal(self):
        report={'same_provider_repeat_build_comparison':{'bclone':{'status':'BYTE_IDENTICAL_UNATTESTED'}},'cross_provider_shared_payload':[],'gate_blockers':{'SB-G01':{'status':'BLOCKED','reasons':['missing']}},'issues':[]}
        self.assertIn('NOT_ISSUED',q13.markdown(report))

    def test_output_symlink_safe(self):
        link=self.base/'out'
        target=self.base/'real';target.mkdir();link.symlink_to(target,target_is_directory=True)
        with self.assertRaises(ValueError):q13.q12.safe_output(link,'skybind-q13-summary.json',b'{}')

if __name__=='__main__':unittest.main()
