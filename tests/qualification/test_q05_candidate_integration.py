"""Q05P1 source integration contract; fixtures never qualify real provider inputs."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts/dev/integration'))
sys.path.insert(0, str(ROOT/'scripts/dev/runtime'))
sys.path.insert(0, str(ROOT/'scripts/dev/release'))
import q05_candidate as q05
import skybind_release as release
import skybind_runtime as rt
import source_build as sb

spec=importlib.util.spec_from_file_location('q04p_fixture',ROOT/'tests/qualification/test_q04p1_build_binding.py')
assert spec and spec.loader
q04=importlib.util.module_from_spec(spec)
spec.loader.exec_module(q04)


def canonical_write(p:Path,obj:dict):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_bytes(sb.canonical(obj))


def staged_fixture(root:Path):
    source, lock = q04.fixture(root)
    artifacts=root/'evidence/artifacts'
    for lane in ('A','B'):
        dest=artifacts/f'skybind-provider-lane-{lane}'
        build=dest/'bclone_build';q04.stage(build,lock)
        packages=dest/'packages';packages.mkdir(parents=True)
        rt.assemble('newfuture',source,packages/'newfuture.zip',lock_path=lock)
        rt.assemble('bclone',source,packages/'bclone.zip',lock_path=lock,bclone_build_dir=build)
        canonical_write(dest/'newfuture-inspection.json', {
            'archive_sha256':rt.filehash(source),'status':'PIN_MATCH_UNATTESTED',
            'gate_g01':'BLOCKED','final_seal':'NOT_ISSUED'})
    comparison=sb.compare(artifacts/'skybind-provider-lane-A/bclone_build',
                          artifacts/'skybind-provider-lane-B/bclone_build',
                          artifacts/'skybind-provider-lane-A/packages',
                          artifacts/'skybind-provider-lane-B/packages')
    canonical_write(artifacts/'skybind-provider-unattested-comparison/comparison.json', comparison)
    run_id=11122233344
    head='c'*40
    run={'headSha':head,'headBranch':'main','status':'completed','conclusion':'success',
         'url':f'https://github.com/Mikeyphw/skybind/actions/runs/{run_id}',
         'workflowName':'Skybind pinned Android providers (UNATTESTED)',
         'jobs':[{'name':name,'conclusion':'success','status':'completed'} for name in (
            'pinned-provider-lanes (A)','pinned-provider-lanes (B)','compare-independent-builds')]}
    canonical_write(root/'evidence/run.json',run)
    selection={'schema_version':1,'kind':'SB_Q04_RAW_BUILD_INPUT_SELECTION_NOT_ATTESTATION',
               'repository':'Mikeyphw/skybind','run_id':run_id,'run_head_sha':head,
               'bclone_commit':q04.COMMIT, 'bclone_binary_sha256':sb.filehash(artifacts/'skybind-provider-lane-A/bclone_build/rclone'),
               'bclone_zip_sha256':sb.filehash(artifacts/'skybind-provider-lane-A/packages/bclone.zip'),
               'newfuture_zip_sha256':sb.filehash(artifacts/'skybind-provider-lane-A/packages/newfuture.zip'),
               'newfuture_original_sha256':rt.filehash(source),
               'gate_g01':'BLOCKED','final_seal':'NOT_ISSUED',
               'independent_attestation':False,'physical_device_tested':False}
    policy=root/'policy.json';canonical_write(policy,selection)
    native=root/'skybind';native.write_bytes(q04.elf());native.chmod(0o755)
    return root/'evidence',policy,lock,native


class Q05CandidateTests(unittest.TestCase):
    def test_source_selection_never_says_sealed(self):
        live=json.loads(q05.INPUTS.read_text())
        self.assertEqual(live['run_id'],38110749243)
        self.assertFalse(live['independent_attestation'])
        self.assertFalse(live['physical_device_tested'])
        self.assertEqual(live['final_seal'],'NOT_ISSUED')
        self.assertEqual(live['gate_g01'],'BLOCKED')

    def test_two_realistic_static_helper_candidates_deterministic(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);e,p,l,n=staged_fixture(root)
            self.assertEqual(q05.evidence_inventory(e,p,l)['comparison']['status'],'BYTE_IDENTICAL_UNATTESTED')
            out=root/'candidates';r=q05.assemble(e,n,out,p,l)
            self.assertEqual(r['status'],'COMPLETE_CANDIDATE_UNQUALIFIED')
            self.assertFalse(r['physical_device_tested'])
            self.assertEqual(r['final_seal'],'NOT_ISSUED')
            for item in r['candidates'].values():
                manifest=release.verify_release(out/item['file'])
                self.assertEqual(manifest['qualification'],'CANDIDATE_ONLY_NOT_SEALED')
            # Rebuild in a second output directory: candidate bytes must be equal.
            again=root/'second';r2=q05.assemble(e,n,again,p,l)
            self.assertEqual(r['candidates'],r2['candidates'])

    def test_missing_and_tampered_run_jobs_denied(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);e,p,l,n=staged_fixture(root)
            original=json.loads((e/'run.json').read_text())
            for update in ({'conclusion':'failure'},{'headSha':'a'*40},{'headBranch':'dev'},
                           {'url':'https://example.com/forge'},{'jobs':original['jobs'][:2]}):
                data=copy.deepcopy(original);data.update(update);canonical_write(e/'run.json',data)
                with self.subTest(update=update),self.assertRaises(q05.Rejected):q05.evidence_inventory(e,p,l)

    def test_changed_comparison_and_fake_seal_denied(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);e,p,l,n=staged_fixture(root)
            selection=json.loads(p.read_text())
            selection['final_seal']='VERIFIED_EXTERNALLY_ISSUED';canonical_write(p,selection)
            with self.assertRaises(q05.Rejected):q05.evidence_inventory(e,p,l)
            selection['final_seal']='NOT_ISSUED';canonical_write(p,selection)
            f=e/'artifacts/skybind-provider-unattested-comparison/comparison.json'
            obj=json.loads(f.read_text());obj['status']='QUALIFIED';canonical_write(f,obj)
            with self.assertRaises(q05.Rejected):q05.evidence_inventory(e,p,l)

    def test_different_second_lane_and_stale_lock_denied(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);e,p,l,n=staged_fixture(root)
            other=l.read_bytes()
            changed=json.loads(other);changed['bclone']['commit']='d'*40;canonical_write(l,changed)
            with self.assertRaises(q05.Rejected):q05.evidence_inventory(e,p,l)
            l.write_bytes(other)
            f=e/'artifacts/skybind-provider-lane-B/packages/bclone.zip'
            with f.open('ab') as out:out.write(b'tamper')
            with self.assertRaises(q05.Rejected):q05.evidence_inventory(e,p,l)

    def test_symlink_evidence_and_native_denied(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);e,p,l,n=staged_fixture(root)
            symlink=root/'linked';symlink.symlink_to(e,target_is_directory=True)
            with self.assertRaises(q05.Rejected):q05.evidence_inventory(symlink,p,l)
            fake=root/'native-link';fake.symlink_to(n)
            with self.assertRaises(q05.Rejected):q05.assemble(e,fake,root/'output',p,l)
            self.assertFalse((root/'output').exists())

    def test_unrecorded_system_member_and_static_helper_mismatch_denied(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);e,p,l,n=staged_fixture(root)
            runtime=e/'artifacts/skybind-provider-lane-A/packages/newfuture.zip'
            import zipfile
            with zipfile.ZipFile(runtime) as z:
                payload={name:z.read(name) for name in z.namelist() if name.startswith('system/') or name=='runtime.provenance.json'}
            release.verify_installed_runtime(payload)
            payload['system/vendor/lib64/extra.so']=q04.elf()
            with self.assertRaises(release.Reject):release.verify_installed_runtime(payload)
            del payload['system/vendor/lib64/extra.so']
            proof=json.loads(payload['runtime.provenance.json']);proof['fuse_delivery']='shared_libfuse'
            payload['runtime.provenance.json']=rt.canonical(proof)
            with self.assertRaises(release.Reject):release.verify_installed_runtime(payload)

    def test_workflow_is_manual_unqualified_and_source_bound(self):
        workflow=(ROOT/'.github/workflows/skybind-candidate-integration.yml').read_text()
        self.assertIn('workflow_dispatch:',workflow)
        self.assertIn('gh run download 38110749243',workflow)
        self.assertIn('CGO_ENABLED: \'0\'',workflow)
        self.assertIn("go-version: '1.27.2'",workflow)
        self.assertIn('q05_candidate.py',workflow)
        self.assertNotIn('release: write',workflow)
        self.assertNotIn('adb install',workflow)
        self.assertIn('CANDIDATES_UNQUALIFIED',workflow)
        reg=(ROOT/'.devtool.toml').read_text()
        self.assertIn('[targets.skybind.jobs.q05-candidate-integration]',reg)

if __name__=='__main__': unittest.main()
