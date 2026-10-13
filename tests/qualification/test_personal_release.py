"""Personal release: convenience never impersonates formal CFS1 qualification."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/dev/integration/personal_release.py'
spec = importlib.util.spec_from_file_location('skybind_personal', SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class PersonalReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.build = self.root / 'build'
        self.dest = self.root / 'downloads'
        self.build.mkdir()
        self.dest.mkdir()
        self.candidate = self.build / 'skybind-bclone-CANDIDATE-UNQUALIFIED.zip'
        self.candidate.write_bytes(b'a' * 512)
        self.digest = hashlib.sha256(self.candidate.read_bytes()).hexdigest()
        self.receipt = self.build / 'candidate-evidence.json'
        self.rec = {
            'build_kind': 'LOCAL_DEVELOPMENT_UNQUALIFIED', 'final_seal': 'NOT_ISSUED',
            'independent_attestation': False, 'physical_device_tested': False,
            'toolchain': 'go1.27.1',
            'q12_source_build': {'commit': 'a' * 40, 'git_clean': True,
                                 'candidate_sha256': {'bclone': self.digest}},
            'candidates': {'bclone': {'file': self.candidate.name, 'sha256': self.digest}},
        }
        self.write_receipt()
    def write_receipt(self):
        self.receipt.write_text(json.dumps(self.rec))
    def publish(self):
        with patch.object(mod.local_build.q05.release, 'verify_release',
                          return_value={'qualification': 'CANDIDATE_ONLY_NOT_SEALED', 'runtime_provider': 'bclone'}) as verify:
            result = mod.package(self.candidate, self.receipt, provider='bclone', dest=self.dest,
                                 timestamp='20261013T120000Z')
            self.assertEqual(verify.call_count, 2)
            return result
    def test_package_no_seal_no_repack_and_consistent_checksums(self):
        res = self.publish()
        archive = Path(res['zip'])
        self.assertEqual(archive.read_bytes(), self.candidate.read_bytes())
        meta = json.loads(Path(res['manifest']).read_text())
        self.assertEqual(meta['track'], 'PERSONAL')
        self.assertEqual(meta['formal_cfs1_seal'], 'NOT_ISSUED')
        self.assertFalse(meta['independent_attestation'])
        self.assertFalse(meta['installed_on_device'])
        self.assertEqual((archive.parent/'SHA256SUMS').read_text().split()[0],self.digest)
    def test_reject_tampered_receipt(self):
        for change in ({'final_seal':'ISSUED'}, {'independent_attestation':True},
                       {'build_kind':'FAKE'}, {'physical_device_tested':True}):
            with self.subTest(change=change):
                original=self.rec.copy();self.rec.update(change);self.write_receipt()
                with self.assertRaises(mod.PersonalError): self.publish()
                self.assertEqual(list(self.dest.iterdir()), [])
                self.rec=original
    def test_reject_wrong_digest(self):
        self.rec['candidates']['bclone']['sha256'] = '0' * 64
        self.write_receipt()
        with self.assertRaises(mod.PersonalError): self.publish()
        self.assertEqual(list(self.dest.iterdir()), [])
    def test_reject_wrong_provider_manifest(self):
        with patch.object(mod.local_build.q05.release, 'verify_release',
                          return_value={'qualification':'CANDIDATE_ONLY_NOT_SEALED','runtime_provider':'newfuture'}):
            with self.assertRaises(mod.PersonalError):
                mod.package(self.candidate,self.receipt,provider='bclone',dest=self.dest)
    def test_reject_symlinks_and_wrong_provider_filename(self):
        link=self.build/'link.zip'; link.symlink_to(self.candidate)
        with self.assertRaises(mod.PersonalError):
            mod.package(link,self.receipt,provider='bclone',dest=self.dest)
        with self.assertRaises(mod.PersonalError):
            mod.package(self.candidate,self.receipt,provider='newfuture',dest=self.dest)
        linked=self.root/'download-link';linked.symlink_to(self.dest,target_is_directory=True)
        with patch.object(mod.local_build.q05.release,'verify_release',return_value={'qualification':'CANDIDATE_ONLY_NOT_SEALED','runtime_provider':'bclone'}):
            with self.assertRaises(mod.PersonalError):
                mod.package(self.candidate,self.receipt,provider='bclone',dest=linked)
    def test_reject_existing_output_no_overwrite(self):
        self.publish()
        with self.assertRaises(mod.PersonalError):self.publish()
        self.assertEqual(len(list(self.dest.iterdir())),1)
    def test_tampered_package_verification_fails_closed(self):
        with patch.object(mod.local_build.q05.release,'verify_release',side_effect=mod.local_build.q05.release.Reject('bad package')):
            with self.assertRaises(mod.local_build.q05.release.Reject):
                mod.package(self.candidate,self.receipt,provider='bclone',dest=self.dest)
        self.assertEqual(list(self.dest.iterdir()), [])
    def test_build_delegates_to_existing_pinned_local_builder(self):
        report={'local_output':str(self.build),'candidates':{'bclone':{'file':self.candidate.name}}}
        with patch.object(mod.local_build,'checked_command') as cmd, patch.object(mod.local_build,'build',return_value=report) as build, patch.object(mod,'package',return_value={'status':'PERSONAL_BUILD_READY'}) as pkg:
            self.assertEqual(mod.personal_build('bclone', self.dest)['status'],'PERSONAL_BUILD_READY')
            self.assertEqual(cmd.call_args.args[0][:3],['go','vet','./...'])
            build.assert_called_once()
            self.assertEqual(build.call_args.kwargs['provider'],'bclone')
            pkg.assert_called_once()
    def test_devtool_commands_and_gates_unchanged(self):
        t=tomllib.loads((ROOT/'.devtool.toml').read_text())
        for cmd, workflow in [('test','personal-tests'), ('personal-release','personal-release-bclone'), ('personal-release-newfuture','personal-release-newfuture')]:
            self.assertEqual(t['wrapper']['commands'][cmd]['workflow'],workflow)
            self.assertEqual(t['targets']['skybind']['workflows'][workflow],['job:'+workflow])
            job=t['targets']['skybind']['jobs'][workflow]
            self.assertFalse(job['metadata']['final_seal'])
            self.assertIn('personal_release.py',job['command'][1])
        for gate in ('scripts/dev/gates/sb_g01.py','scripts/dev/gates/sb_g02.py','scripts/dev/seal/sb_cfs1.py'):
            self.assertTrue((ROOT/gate).is_file())

if __name__=='__main__':unittest.main()
