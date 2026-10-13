"""SB-Q14: authenticated original CI evidence, no false signed status."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('q14_under_test',HERE/'scripts/dev/release/q14_attestation.py')
q14=importlib.util.module_from_spec(spec)
spec.loader.exec_module(q14)
SHA='a'*40
DIG='b'*64


def run_response():
    return {'id': 38328621356, 'workflow_id': 123, 'status':'completed',
            'conclusion':'success', 'head_sha':SHA, 'event':'workflow_dispatch',
            'repository': {'full_name':'Mikeyphw/skybind'}, 'html_url':'https://github.com/Mikeyphw/skybind/actions/runs/38328621356'}

class Q14Tests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup)
        self.base=Path(t.name)

    def test_authenticated_run_exact_identity(self):
        def cli(args,**kw):
            return json.dumps(run_response() if args[-1].endswith('/38328621356') else
                              {'path':'.github/workflows/skybind-q13-candidate-reproducibility.yml'})
        with patch.object(q14,'execute',side_effect=cli):
            report=q14.authenticated_run('Mikeyphw/skybind',38328621356)
        self.assertEqual(report['head_sha'],SHA)
        self.assertEqual(report['workflow'],'skybind-q13-candidate-reproducibility.yml')

    def test_reject_failed_run(self):
        data=run_response();data['conclusion']='failure'
        with patch.object(q14,'execute',side_effect=[json.dumps(data),json.dumps({'path':'.github/workflows/skybind-q13-candidate-reproducibility.yml'})]):
            with self.assertRaisesRegex(ValueError,'NOT_SUCCESSFUL'):
                q14.authenticated_run('Mikeyphw/skybind',38328621356)

    def test_reject_wrong_workflow(self):
        with patch.object(q14,'execute',side_effect=[json.dumps(run_response()),json.dumps({'path':'.github/workflows/other.yml'})]):
            with self.assertRaisesRegex(ValueError,'UNRECOGNIZED'):
                q14.authenticated_run('Mikeyphw/skybind',38328621356)

    def test_reject_cross_repo_and_untrusted_repo(self):
        d=run_response();d['repository']['full_name']='someone_else/different'
        with patch.object(q14,'execute',side_effect=[json.dumps(d),json.dumps({'path':'.github/workflows/skybind-q13-candidate-reproducibility.yml'})]):
            with self.assertRaisesRegex(ValueError,'REPOSITORY_MISMATCH'):
                q14.authenticated_run('Mikeyphw/skybind',38328621356)
        with self.assertRaises(ValueError):q14.authenticated_run('Mikeyphw/skybind;cat',38328621356)

    def test_verify_subject_is_necessary(self):
        valid=[{'verificationResult':{'statement':{'predicateType':'https://slsa.dev/provenance/v1',
                 'subject':[{'digest':{'sha256':DIG}}]}}}]
        self.assertTrue(q14.validated_subjects(valid,DIG))
        self.assertFalse(q14.validated_subjects([],DIG))
        self.assertFalse(q14.validated_subjects(valid,'c'*64))
        valid[0]['verificationResult']['statement']['predicateType']='not-slsa'
        self.assertFalse(q14.validated_subjects(valid,DIG))

    def test_attestation_real_sigstore_cli_required(self):
        folder=self.base/'lane';folder.mkdir()
        item=folder/'skybind-bclone-CANDIDATE-UNQUALIFIED.zip';item.write_bytes(b'candidate')
        s=q14.hashlib.sha256(item.read_bytes()).hexdigest()
        response=[{'verificationResult':{'statement':{'predicateType':'https://slsa.dev/provenance/v1',
                 'subject':[{'digest':{'sha256':s}}]}}}]
        run={'workflow':'skybind-q14-attested-candidates.yml','head_sha':SHA}
        calls=[]
        def cli(args):
            calls.extend(args)
            return json.dumps(response)
        res=q14.attest('Mikeyphw/skybind',run,folder,'bclone',cli=cli)
        self.assertEqual(res['status'],'GH_SIGNED_SOURCE_AND_SUBJECT_VERIFIED_NOT_CFS1')
        self.assertIn('--source-digest',calls)
        self.assertIn('--signer-workflow',calls)
        self.assertIn('--deny-self-hosted-runners',calls)
        self.assertIn('--repo',calls)
        self.assertNotIn('ISSUED',res['status'])

    def test_no_signature_never_passes(self):
        folder=self.base/'lane';folder.mkdir()
        (folder/'skybind-newfuture-CANDIDATE-UNQUALIFIED.zip').write_bytes(b'raw')
        run={'workflow':'skybind-q13-candidate-reproducibility.yml','head_sha':SHA}
        res=q14.attest('Mikeyphw/skybind',run,folder,'newfuture',cli=lambda _:(_ for _ in ()).throw(RuntimeError('not found')))
        self.assertEqual(res['status'],'NO_Q13_ATTESTATIONS_EXPECTED')
        run['workflow']='skybind-q14-attested-candidates.yml'
        res=q14.attest('Mikeyphw/skybind',run,folder,'newfuture',cli=lambda _:(_ for _ in ()).throw(RuntimeError('bad certificate')))
        self.assertEqual(res['status'],'ATTESTATION_UNAVAILABLE_OR_REJECTED')

    def test_fresh_directory_only(self):
        folder=self.base/'skybind-q14-run-38328621356';folder.mkdir()
        with patch.object(q14,'authenticated_run',return_value={'workflow':'skybind-q13-candidate-reproducibility.yml'}):
            with self.assertRaisesRegex(ValueError,'DIRECTORY_EXISTS'):
                q14.local_evaluate('Mikeyphw/skybind',38328621356,self.base,self.base)

    def test_download_allowlist_fail_closed(self):
        def cli(args,**kw):
            (Path(args[-1])/'not-the-real-candidate.zip').write_bytes(b'fake')
            return ''
        with patch.object(q14,'execute',side_effect=cli):
            with self.assertRaisesRegex(ValueError,'UNEXPECTED_CI_LANE'):
                q14.fetch_lanes('Mikeyphw/skybind',38328621356,'skybind-q13-candidate-',self.base)

    def test_output_symlink_rejected(self):
        real=self.base/'real';real.mkdir()
        link=self.base/'linked';link.symlink_to(real,target_is_directory=True)
        with self.assertRaises(ValueError):q14.save(link,'skybind-q14-summary.json',b'{}')
        dest=real/'skybind-q14-summary.json';dest.symlink_to(self.base/'other')
        with self.assertRaises(ValueError):q14.save(real,'skybind-q14-summary.json',b'{}')

    def test_report_never_claims_signed_gate(self):
        report={'run':{'run_id':1,'workflow':'skybind-q13-candidate-reproducibility.yml'},
                'same_provider':{p:{'status':'BYTE_IDENTICAL_UNATTESTED'} for p in q14.PROVIDERS},
                'signed_candidate_provenance':{a:{p:{'status':'SIGNATURE_NOT_VERIFIED'} for p in q14.PROVIDERS} for a in ('A','B')},
                'independent_gate_evaluation':{'SB-G01':{'status':'BLOCKED','reasons':['evidence missing']}}}
        text=q14.markdown(report)
        self.assertIn('NOT_ISSUED',text)
        self.assertIn('BLOCKED',text)

if __name__=='__main__': unittest.main()
