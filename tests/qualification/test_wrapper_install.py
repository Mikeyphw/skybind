"""Optional KernelSU install and bounded build-retention contract tests."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts/dev/integration'))
import module_install
import local_build
import personal_release


class WrapperInstallTests(unittest.TestCase):
    def test_wrapper_install_and_plain_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / 'devtool_stub'
            fake.write_text('#!/bin/sh\nprintf "%s\n" "$@"\n')
            fake.chmod(0o755)
            env = dict(os.environ, DEVTOOL_WRAPPER_EXECUTABLE=str(fake))
            cases = [
                (['build'], 'build'),
                (['build', '-i'], 'build-install'),
                (['build', '--install'], 'build-install'),
                (['build-bclone', '-i'], 'build-bclone-install'),
                (['build-newfuture', '--install'], 'build-newfuture-install'),
                (['personal-release', '-i'], 'personal-release-install'),
                (['personal-release-newfuture', '--install'], 'personal-release-newfuture-install'),
                (['build-both'], 'build-both'),
            ]
            for argv, intended in cases:
                with self.subTest(argv=argv):
                    out = subprocess.run([str(ROOT/'devtoolw'), *argv], env=env, capture_output=True, text=True, cwd=tmp)
                    self.assertEqual(out.returncode, 0, out.stderr)
                    self.assertEqual(out.stdout.splitlines()[-1], intended)
            for bad in (['build-both', '-i'], ['build', '-i', '--oops']):
                out = subprocess.run([str(ROOT/'devtoolw'), *bad], env=env, capture_output=True, text=True)
                self.assertEqual(out.returncode, 2)
                self.assertEqual(out.stdout, '')

    def test_devtool_install_jobs_provenance(self):
        cfg = tomllib.loads((ROOT/'.devtool.toml').read_text())
        commands = cfg['wrapper']['commands']
        jobs = cfg['targets']['skybind']['jobs']
        flows = cfg['targets']['skybind']['workflows']
        mappings = {
            'build-install':'local-build-newfuture-install',
            'build-newfuture-install':'local-build-newfuture-install',
            'build-bclone-install':'local-build-bclone-install',
            'personal-release-install':'personal-release-bclone-install',
            'personal-release-newfuture-install':'personal-release-newfuture-install',
        }
        for name, flow in mappings.items():
            self.assertEqual(commands[name]['workflow'], flow)
            self.assertEqual(flows[flow], ['job:'+flow])
            self.assertIn('--install', jobs[flow]['command'])
            self.assertTrue(jobs[flow]['metadata']['installed_module_mutation'])
            self.assertFalse(jobs[flow]['metadata']['final_seal'])

    def test_install_uses_literal_su_and_streams_both_fds(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / 'Skybind bclone PERSONAL.zip'
            file.write_bytes(b'fixture')
            verified = {'qualification':'CANDIDATE_ONLY_NOT_SEALED', 'runtime_provider':'bclone'}
            with patch.object(module_install.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
                module_install.install_verified_zip(file, provider='bclone', release_verify=lambda _: verified)
                args, kw = run.call_args
                self.assertEqual(args[0][0:2], ['su','-c'])
                self.assertIn('ksud module install ', args[0][2])
                self.assertIn("Skybind bclone PERSONAL.zip'", args[0][2])
                self.assertNotIn('stdout', kw)
                self.assertNotIn('stderr', kw)
                self.assertFalse(kw['check'])
            with patch.object(module_install.subprocess, 'run', return_value=subprocess.CompletedProcess([], 42)):
                with self.assertRaisesRegex(module_install.ModuleInstallError, 'exit 42'):
                    module_install.install_verified_zip(file, provider='bclone', release_verify=lambda _: verified)
            with patch.object(module_install.subprocess, 'run') as run:
                with self.assertRaisesRegex(module_install.ModuleInstallError, 'provider/qualification mismatch'):
                    module_install.install_verified_zip(file, provider='newfuture', release_verify=lambda _: verified)
                run.assert_not_called()

    def test_candidate_retention_only_removes_owned_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            newest = root/'candidate-current'; newest.mkdir()
            owned = root/'candidate-old'; owned.mkdir()
            data = {'build_kind':'LOCAL_DEVELOPMENT_UNQUALIFIED','final_seal':'NOT_ISSUED',
                    'candidates':{'bclone':{'file':'skybind-bclone-CANDIDATE-UNQUALIFIED.zip'}}}
            (owned/'candidate-evidence.json').write_text(json.dumps(data))
            (owned/'skybind-bclone-CANDIDATE-UNQUALIFIED.zip').write_bytes(b'ok')
            foreign = root/'candidate-user'; foreign.mkdir()
            (foreign/'notes.txt').write_text('protected')
            link = root/'candidate-link'; link.symlink_to(foreign, target_is_directory=True)
            self.assertEqual(local_build.prune_managed_candidates(root, keep=newest), 1)
            self.assertFalse(owned.exists())
            self.assertTrue(foreign.exists())
            self.assertTrue(link.is_symlink())
            self.assertTrue(newest.exists())

    def test_personal_retention_only_removes_owned_exports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            newest = root/'Skybind-Personal-bclone-20261015T120000Z-abcdef123456'; newest.mkdir()
            old = root/'Skybind-Personal-newfuture-20261014T120000Z-abcdef123456'; old.mkdir()
            (old/'PERSONAL_BUILD.json').write_text(json.dumps({'track':'PERSONAL','product':'skybind',
               'formal_cfs1_seal':'NOT_ISSUED','archive':'Skybind-newfuture-PERSONAL.zip'}))
            for n in ['Skybind-newfuture-PERSONAL.zip','SHA256SUMS','README.txt']:
                (old/n).write_text('fixture')
            keep = root/'Skybind-Personal-bclone-20261012T120000Z-abcdef123456'; keep.mkdir()
            (keep/'personal-notes').write_text('protected')
            self.assertEqual(personal_release.prune_personal_exports(root, keep=newest), 1)
            self.assertFalse(old.exists())
            self.assertTrue(keep.exists())
            self.assertTrue(newest.exists())

    def test_cli_rejects_ambiguous_install_before_build(self):
        with patch.object(sys, 'argv', ['local_build.py', '--provider', 'both', '--install']):
            with self.assertRaises(SystemExit) as failure:
                local_build.main()
            self.assertEqual(failure.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
