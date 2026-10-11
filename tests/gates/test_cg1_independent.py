"""Gate definition regression: fail-closed and no false device/release claims."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/dev/gates'))
import sb_cg1 as gates

class IndependentMilestones(unittest.TestCase):
    def test_original_dependencies_frozen(self):
        original=json.loads((ROOT/'docs/roadmap/SKYBIND_ORIGINAL_45_ITEM_INDEX.json').read_text())
        self.assertEqual(len(gates.GATES),6)
        for i,gate in enumerate(original['gate_overlays'][2:]):
            self.assertEqual(gates.read_ledger(ROOT,gate['id'])['dependencies'],gate['dependencies'])
            self.assertEqual(gates.GATES[i],gate['id'])

    def test_all_six_blocked_with_upstream_and_external_evidence_absent(self):
        with patch.dict(os.environ,{'SKYBIND_VERIFIED_GATE_EVIDENCE_DIR':'','SKYBIND_GATE_TRUST_PUBKEY':'','SKYBIND_GATE_TRUST_KEY_SHA256':''}):
            result=gates.evaluate_all(ROOT)
        self.assertEqual(result['dependency_gates'],{'SB-G01':'BLOCKED','SB-G02':'BLOCKED'})
        self.assertEqual(result['status'],'BLOCKED')
        self.assertEqual(result['final_seal'],'NOT_ISSUED')
        for name,item in result['gates'].items():
            self.assertEqual(item['status'],'BLOCKED')
            self.assertTrue(item['reasons'])
            self.assertEqual(item['final_seal'],'NOT_ISSUED')
            self.assertEqual(len(item['source_scope_sha256']),64)
        self.assertEqual(result['android_device'],'NOT_ATTESTED')

    def test_digest_detects_source_content_and_symlink(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p=root/'source';p.mkdir();f=p/'a.go';f.write_text('original')
            first=gates.source_digest(root,['source']);f.write_text('changed')
            self.assertNotEqual(first,gates.source_digest(root,['source']))
            f.unlink();f.symlink_to(root/'elsewhere')
            with self.assertRaises(ValueError):gates.source_digest(root,['source'])

    def test_no_unsigned_or_in_repo_evidence(self):
        ledger=gates.read_ledger(ROOT,'SB-G03')
        with tempfile.TemporaryDirectory() as t:
            outside=Path(t);key=outside/'key.pub';key.write_bytes(b'not-real')
            with patch.dict(os.environ,{
                    'SKYBIND_VERIFIED_GATE_EVIDENCE_DIR':str(ROOT/'docs'),
                    'SKYBIND_GATE_TRUST_PUBKEY':str(key),
                    'SKYBIND_GATE_TRUST_KEY_SHA256':gates.sha(key.read_bytes())}):
                reasons=gates._verified_attestation(ROOT,'SB-G03','a'*64,'b'*40,ledger)
            self.assertIn('EVIDENCE_OR_TRUST_KEY_INSIDE_REPOSITORY',reasons)

    def test_wrong_trust_key_pin_denied(self):
        ledger=gates.read_ledger(ROOT,'SB-G03')
        with tempfile.TemporaryDirectory() as t:
            d=Path(t);key=d/'key.pub';key.write_bytes(b'a')
            with patch.dict(os.environ,{'SKYBIND_VERIFIED_GATE_EVIDENCE_DIR':str(d),
                    'SKYBIND_GATE_TRUST_PUBKEY':str(key),'SKYBIND_GATE_TRUST_KEY_SHA256':'0'*64}):
                reasons=gates._verified_attestation(ROOT,'SB-G03','a'*64,'b'*40,ledger)
            self.assertIn('TRUST_KEY_PIN_INVALID',reasons)

    def test_missing_signature_denied_even_with_correct_key_digest(self):
        ledger=gates.read_ledger(ROOT,'SB-G08')
        with tempfile.TemporaryDirectory() as t:
            d=Path(t);key=d/'key.pub';key.write_bytes(b'a')
            with patch.dict(os.environ,{'SKYBIND_VERIFIED_GATE_EVIDENCE_DIR':str(d),
                    'SKYBIND_GATE_TRUST_PUBKEY':str(key),'SKYBIND_GATE_TRUST_KEY_SHA256':gates.sha(key.read_bytes())}):
                reasons=gates._verified_attestation(ROOT,'SB-G08','a'*64,'b'*40,ledger)
            self.assertIn('SIGNED_GATE_ATTESTATION_MISSING',reasons)

    def test_cli_gate_is_blocked_not_crashed(self):
        p=subprocess.run([sys.executable,str(ROOT/'scripts/dev/gates/sb_cg1.py'),'--gate','SB-G07'],capture_output=True,text=True)
        self.assertEqual(p.returncode,3,p.stderr)
        d=json.loads(p.stdout);self.assertEqual(d['status'],'BLOCKED')
        self.assertIn('DEPENDENCY_BLOCKED_SB-G06',d['reasons'])

    def test_gate_runs_do_not_modify_product_source(self):
        files=[ROOT/'internal/control/control.go',ROOT/'internal/daemon/wiring.go']
        before=[gates.sha(x.read_bytes()) for x in files]
        gates.evaluate_all(ROOT)
        self.assertEqual(before,[gates.sha(x.read_bytes()) for x in files])

    def test_gate_signed_result_cannot_cross_dependency(self):
        with patch.object(gates,'_verified_attestation',return_value=[]):
            data=gates.evaluate_all(ROOT)
        self.assertEqual(data['gates']['SB-G03']['status'],'BLOCKED')
        self.assertEqual(data['gates']['SB-G08']['status'],'BLOCKED')

if __name__=='__main__':unittest.main()
