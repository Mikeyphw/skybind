"""SB-Q12: fail-closed local inventory + no fake independent qualification."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

HERE = Path(__file__).resolve().parents[2]
FILE = HERE / 'scripts/dev/release/q12_provenance.py'
spec = importlib.util.spec_from_file_location('q12_provenance', FILE)
q12 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q12)

H = lambda blob: hashlib.sha256(blob).hexdigest()


class TestQ12(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.evidence = self.dir / 'evidence'
        self.evidence.mkdir()
        self.zip = self.dir / 'skybind-bclone-CANDIDATE-UNQUALIFIED.zip'
        self.payload = {name: (name + '-bytes').encode() for name in q12.FILES}
        with zipfile.ZipFile(self.zip, 'w') as z:
            for name, content in self.payload.items():
                z.writestr(name, content)
        self.installed = self.dir / 'installed'
        for name, content in self.payload.items():
            p = self.installed / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content)
        self.manifest = {'qualification': 'CANDIDATE_ONLY_NOT_SEALED', 'runtime_provider': 'bclone',
                         'files': {name: {'sha256': H(content), 'size': len(content)} for name, content in self.payload.items()}}
        self.source = {'commit': '1' * 40, 'tree': '2' * 40, 'worktree_clean': True, 'frozen_against_device_binary': False}
        self.gate = {'status': 'BLOCKED', 'final_seal': 'NOT_ISSUED', 'milestone_gates': {f'SB-G{i:02d}': 'BLOCKED' for i in range(1, 9)}}

    def test_candidate_requires_authoritative_verification(self):
        with patch.object(q12.release, 'verify_release', return_value=self.manifest):
            obj = q12.inspect_candidate(self.zip)
        self.assertEqual(obj['status'], 'VALID_UNQUALIFIED_CANDIDATE')
        self.assertEqual(obj['members']['system/bin/skybind'], H(self.payload['system/bin/skybind']))

    def test_candidate_verifier_failure_is_not_pass(self):
        with patch.object(q12.release, 'verify_release', side_effect=q12.release.Reject('tampered')):
            obj = q12.inspect_candidate(self.zip)
        self.assertEqual(obj['status'], 'INVALID')
        self.assertIsNone(obj['sha256'])

    def test_symlink_candidate_is_rejected(self):
        link = self.dir / 'link.zip'
        link.symlink_to(self.zip)
        self.assertEqual(q12.inspect_candidate(link)['status'], 'INVALID')

    def test_installed_binary_absence_is_not_observed(self):
        (self.installed/'system/bin/skybind').unlink()
        self.assertEqual(q12.inspect_installed(fixture=self.installed)['status'], 'INCOMPLETE_OR_NO_ROOT_ACCESS')

    def test_installed_symlink_is_not_observed(self):
        file = self.installed / 'system/bin/skybind'
        file.unlink()
        file.symlink_to(self.zip)
        self.assertIsNone(q12.inspect_installed(fixture=self.installed)['members']['system/bin/skybind'])

    def test_explicit_candidate_vs_ambiguous(self):
        root = self.dir / 'root'; base = root/'dist/local-candidates'
        for n in ('candidate-a','candidate-b'):
            p = base/n/'skybind-bclone-CANDIDATE-UNQUALIFIED.zip'
            p.parent.mkdir(parents=True)
            p.write_bytes(b'bad')
        selected, status = q12.candidates(root, None)
        self.assertIsNone(selected)
        self.assertEqual(status, 'AMBIGUOUS_CANDIDATES_EXPLICIT_SELECTION_REQUIRED')
        self.assertEqual(q12.candidates(root, self.zip), (self.zip, 'EXPLICIT'))

    def test_old_receipt_does_not_invent_source_binding(self):
        obj = q12.inspect_build_receipt(self.zip, {'status':'VALID_UNQUALIFIED_CANDIDATE','provider':'bclone','sha256':H(self.zip.read_bytes())}, self.dir, self.source)
        self.assertEqual(obj['source_to_candidate'], 'NOT_PROVEN')

    def receipt(self, *, match=True, dirty=False):
        record = {'schema_version':1, 'commit': self.source['commit'], 'tree': self.source['tree'],
                  'git_clean': not dirty, 'candidate_sha256': {'bclone': H(self.zip.read_bytes()) if match else 'c'*64},
                  'assurance':'LOCAL_SELF_REPORTED_BUILD_TIME_NOT_ATTESTED'}
        data = {'final_seal':'NOT_ISSUED','independent_attestation':False,'build_kind':'LOCAL_DEVELOPMENT_UNQUALIFIED',
                'candidates':{'bclone':{'file':self.zip.name,'sha256':H(self.zip.read_bytes())}},'q12_source_build':record}
        (self.dir/'candidate-evidence.json').write_text(json.dumps(data))

    def test_build_receipt_matches_but_cannot_attest(self):
        self.receipt()
        obj = q12.inspect_build_receipt(self.zip, {'status':'VALID_UNQUALIFIED_CANDIDATE','provider':'bclone','sha256':H(self.zip.read_bytes())}, self.dir, self.source)
        self.assertEqual(obj['source_to_candidate'], 'LOCAL_SELF_REPORTED_ONLY')

    def test_build_receipt_mismatch_fails_closed(self):
        self.receipt(match=False)
        obj = q12.inspect_build_receipt(self.zip, {'status':'VALID_UNQUALIFIED_CANDIDATE','provider':'bclone','sha256':H(self.zip.read_bytes())}, self.dir, self.source)
        self.assertEqual(obj['status'], 'INVALID_BUILD_RECEIPT')

    def test_dirty_at_build_does_not_bind(self):
        self.receipt(dirty=True)
        obj = q12.inspect_build_receipt(self.zip, {'status':'VALID_UNQUALIFIED_CANDIDATE','provider':'bclone','sha256':H(self.zip.read_bytes())}, self.dir, self.source)
        self.assertEqual(obj['source_to_candidate'], 'NOT_PROVEN')

    def run_reconcile(self, *, modify=None, baseline=None):
        with patch.object(q12.release,'verify_release',return_value=self.manifest), \
             patch.object(q12,'source_identity',return_value=self.source), \
             patch.object(q12,'get_baseline',return_value=baseline or {'status':'RAW_BASELINE_CHECKSUM_VERIFIED','binary_sha256':H(self.payload['system/bin/skybind'])}), \
             patch.object(q12.q11,'evaluate_gates',return_value=self.gate):
            if modify:
                modify()
            return q12.reconcile(self.dir,self.evidence,self.zip,fixture=self.installed)

    def test_matching_hashes_only_local(self):
        result = self.run_reconcile()
        self.assertEqual(result['bindings']['candidate_to_installed'],'LOCAL_HASH_MATCH_NOT_ATTESTED')
        self.assertEqual(result['bindings']['q09_baseline_to_candidate'],'RAW_HASH_MATCH_NOT_ATTESTED')
        self.assertEqual(result['bindings']['independent_source_build_device'],'NOT_PROVEN')
        self.assertEqual(result['final_seal'],'NOT_ISSUED')

    def test_tampered_installed_file_rejected(self):
        obj = self.run_reconcile(modify=lambda: (self.installed/'system/bin/rclone').write_bytes(b'changed'))
        self.assertEqual(obj['bindings']['candidate_to_installed'],'NOT_PROVEN')
        self.assertEqual(obj['bindings']['q09_baseline_to_candidate'],'NOT_PROVEN')

    def test_wrong_q09_baseline_not_bound(self):
        obj = self.run_reconcile(baseline={'status':'RAW_BASELINE_CHECKSUM_VERIFIED','binary_sha256':'f'*64})
        self.assertEqual(obj['bindings']['candidate_to_installed'],'LOCAL_HASH_MATCH_NOT_ATTESTED')
        self.assertEqual(obj['bindings']['q09_baseline_to_candidate'],'NOT_PROVEN')

    def test_symlink_output_is_refused(self):
        dest = self.dir/'dest'; dest.mkdir()
        (dest/'skybind-q12-summary.json').symlink_to(self.zip)
        with self.assertRaises(ValueError):
            q12.safe_output(dest,'skybind-q12-summary.json',b'{}')

    def test_atomic_report_writes(self):
        q12.safe_output(self.dir,'skybind-q12-summary.json',b'{}')
        self.assertEqual((self.dir/'skybind-q12-summary.json').read_bytes(),b'{}')

    def test_fixed_root_command_not_user_provided(self):
        with patch.object(q12.subprocess,'run') as execute:
            execute.return_value.returncode = 0
            execute.return_value.stdout = 'a'*64 + '  /data/adb/modules/skybind/system/bin/skybind\n'
            self.assertEqual(q12._root_hash('system/bin/skybind'),'a'*64)
            args = execute.call_args.args[0]
            self.assertEqual(args[0:2],['su','-c'])
            self.assertEqual(args[2],'/system/bin/sha256sum /data/adb/modules/skybind/system/bin/skybind')

    def test_missing_root_does_not_fake_proof(self):
        with patch.object(q12.subprocess,'run',side_effect=FileNotFoundError):
            self.assertIsNone(q12._root_hash('system/bin/skybind'))

    def test_cfs1_blocked_is_preserved(self):
        obj=self.run_reconcile()
        self.assertTrue(all(s=='BLOCKED' for s in obj['independent_gate_evaluation']['milestone_gates'].values()))
        self.assertNotIn('QUALIFIED',obj['status'])


if __name__=='__main__':
    unittest.main()
