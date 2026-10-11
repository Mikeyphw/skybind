"""SB-Q05P7 local wrappers: no unpinned provider / no accidental seal."""
import importlib.util
import json
import io
import contextlib
import time
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/dev/integration'))
import local_build as local
import q05_candidate as q05

spec = importlib.util.spec_from_file_location('q05_fixture', ROOT/'tests/qualification/test_q05_candidate_integration.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class LocalWrappers(unittest.TestCase):
    def test_nexus_style_wrapper_registration(self):
        cfg = tomllib.loads((ROOT/'.devtool.toml').read_text())
        wrappers = cfg['wrapper']['commands']
        expected = {
            'build': ('local-build-newfuture', 'local-build-newfuture'),
            'build-newfuture': ('local-build-newfuture', 'local-build-newfuture'),
            'build-bclone': ('local-build-bclone', 'local-build-bclone'),
            'build-both': ('local-build-both', 'local-build-both'),
            'runtime-newfuture': ('local-runtime-newfuture', 'local-runtime-newfuture'),
            'runtime-bclone': ('local-runtime-bclone', 'local-runtime-bclone'),
        }
        workflows = cfg['targets']['skybind']['workflows']
        jobs = cfg['targets']['skybind']['jobs']
        for name, (workflow, job) in expected.items():
            self.assertEqual(wrappers[name]['target'], 'skybind')
            self.assertEqual(wrappers[name]['workflow'], workflow)
            self.assertEqual(workflows[workflow], ['job:'+job])
            self.assertFalse(jobs[job]['metadata']['final_seal'])
            cmd = jobs[job]['command']
            self.assertEqual(cmd[:2], ['python3', 'scripts/dev/integration/local_build.py'])
            self.assertNotIn('release', cmd)

    def test_selected_go_accepts_exact_local_1271_compatibility_only(self):
        with patch.object(local, 'checked_command', return_value=subprocess.CompletedProcess([], 0, stdout=b'go version go1.27.1 android/arm64\n')):
            with contextlib.redirect_stdout(io.StringIO()) as messages:
                version, env = local.selected_go('go')
            self.assertEqual(version, '1.27.1')
            self.assertIn('LOCAL, UNQUALIFIED', messages.getvalue())
            self.assertIn('CI source pin remains Go 1.27.2', messages.getvalue())
            self.assertEqual(env['GOTOOLCHAIN'], 'local')
            self.assertEqual(env['CGO_ENABLED'], '0')
        with patch.object(local, 'checked_command', return_value=subprocess.CompletedProcess([], 0, stdout=b'go version go1.27.2 android/arm64\n')):
            version, env = local.selected_go('go')
            self.assertEqual(version, '1.27.2')
            self.assertEqual(env['GOTOOLCHAIN'], 'local')

    def test_other_compilers_remain_rejected_before_evidence_download(self):
        for version in ('1.27.0','1.27.3','1.26.5','1.28.0'):
            with self.subTest(version=version), patch.object(local, 'checked_command', return_value=subprocess.CompletedProcess([], 0, stdout=f'go version go{version} android/arm64\n'.encode())):
                with self.assertRaisesRegex(local.LocalBuildError, 'No provider download'):
                    local.selected_go('go')
        with patch.object(local, 'checked_command', return_value=subprocess.CompletedProcess([], 0, stdout=b'garbled untrusted version\n')):
            with self.assertRaises(local.LocalBuildError):
                local.selected_go('go')

    def test_mismatched_ci_lock_does_not_authorize_fallback(self):
        with patch.object(local.q05, 'json_input', return_value={'bclone': {'go_version': '1.27.3'}}), \
                patch.object(local, 'checked_command', return_value=subprocess.CompletedProcess([], 0, stdout=b'go version go1.27.1 android/arm64\n')):
            with self.assertRaisesRegex(local.LocalBuildError, 'CI pin is 1.27.2'):
                local.selected_go('go')

    def test_local_candidate_receipt_records_actual_not_selected_compiler(self):
        for version, matches in (('1.27.1', False), ('1.27.2', True)):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as tmp:
                report = {'final_seal':'NOT_ISSUED','gate_g01':'BLOCKED',
                          'independent_attestation':False,'physical_device_tested':False}
                local.record_local_toolchain(Path(tmp),report,version,'1.27.2')
                disk = json.loads((Path(tmp)/'candidate-evidence.json').read_text())
                self.assertEqual(disk['toolchain'],'go'+version)
                self.assertEqual(disk['selected_ci_toolchain'],'go1.27.2')
                self.assertEqual(disk['local_go_matches_ci_pin'], matches)
                self.assertEqual(disk['final_seal'],'NOT_ISSUED')
                self.assertFalse(disk['independent_attestation'])
                self.assertEqual(disk['build_kind'],'LOCAL_DEVELOPMENT_UNQUALIFIED')
        with tempfile.TemporaryDirectory() as tmp:
            good={'final_seal':'NOT_ISSUED','gate_g01':'BLOCKED',
                  'independent_attestation':False,'physical_device_tested':False}
            for altered in (dict(good,final_seal='ISSUED'), dict(good,independent_attestation=True)):
                with self.assertRaises(local.LocalBuildError):
                    local.record_local_toolchain(Path(tmp),altered,'1.27.1','1.27.2')
            with self.assertRaises(local.LocalBuildError):
                local.record_local_toolchain(Path(tmp),good,'1.27.3','1.27.2')

    def test_native_metadata_rejects_wrong_local_compiler(self):
        with tempfile.TemporaryDirectory() as tmp:
            elf=Path(tmp)/'skybind'
            elf.write_bytes(b'fixture')
            env={'GOTOOLCHAIN':'local'}
            good = b'file: go1.27.1\n  build GOOS=android\n  build GOARCH=arm64\n  build CGO_ENABLED=0\n'
            with patch.object(local.q05.release, 'is_arm64_elf', return_value=True), \
                 patch.object(local, 'checked_command', return_value=subprocess.CompletedProcess([],0,stdout=good)):
                local.verify_native(elf,'1.27.1','go',env)
                with self.assertRaisesRegex(local.LocalBuildError,'metadata mismatches'):
                    local.verify_native(elf,'1.27.2','go',env)

    def test_invalid_source_cannot_reach_local_compile(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / 'missing'
            with patch.object(local, 'selected_go') as go:
                with self.assertRaises(q05.Rejected):
                    local.build(provider='bclone', existing_evidence=evidence)
                go.assert_not_called()
            with self.assertRaisesRegex(local.LocalBuildError, 'invalid provider'):
                local.build(provider='mutable-upstream')

    def test_single_provider_modules_from_exact_q04_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence,policy,lock,native = fixture.staged_fixture(root)
            for provider in ('newfuture','bclone'):
                out = root / provider
                report=q05.assemble(evidence,native,out,policy,lock,providers=(provider,))
                self.assertEqual(set(report['candidates']), {provider})
                self.assertEqual(report['final_seal'], 'NOT_ISSUED')
                self.assertFalse(report['independent_attestation'])
                self.assertEqual(len(list(out.glob('*.zip'))),1)
                self.assertEqual(q05.release.verify_release(next(out.glob('*.zip')))['qualification'],
                                 'CANDIDATE_ONLY_NOT_SEALED')
            for selection in ((), ('newfuture','newfuture'), ('random',)):
                with self.subTest(selection=selection), self.assertRaises(q05.Rejected):
                    q05.assemble(evidence,native,root/'invalid',policy,lock,providers=selection)

    def test_build_never_uses_upstream_mutable_tags_or_seal(self):
        text = (ROOT/'scripts/dev/integration/local_build.py').read_text()
        self.assertIn('q05.evidence_inventory', text)
        self.assertIn('q05.release.verify_release', text)
        self.assertIn("'GOTOOLCHAIN': 'local'",text)
        self.assertIn('GOARCH=arm64', text)
        self.assertNotIn('git clone', text)
        self.assertNotIn('sdkmanager', text)
        self.assertNotIn('force-push', text)
        self.assertIn('CANDIDATE_ONLY_NOT_SEALED', text)

    def test_wrong_go_fails_before_remote_evidence_is_fetched(self):
        """Regression for the reported ~108-second silent download then failure."""
        with patch.object(local, 'selected_go', side_effect=local.LocalBuildError('wrong Go')):
            with patch.object(local, 'evidence_root') as evidence:
                with self.assertRaisesRegex(local.LocalBuildError, 'wrong Go'):
                    local.build(provider='bclone')
                evidence.assert_not_called()

    def test_readable_missing_go_error(self):
        with patch.object(local, 'checked_command', return_value=subprocess.CompletedProcess(
                ['go', 'version'], 0, stdout=b'go version go1.26.5 android/arm64\n')):
            with contextlib.redirect_stdout(io.StringIO()) as messages:
                with self.assertRaisesRegex(local.LocalBuildError, 'found go1.26.5') as error:
                    local.selected_go('go')
            self.assertIn('Toolchain preflight', messages.getvalue())
            self.assertIn('SKYBIND_LOCAL_GO_BIN', str(error.exception))

    def test_long_command_heartbeat_and_no_provider_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(local, 'LOG_INTERVAL_SECONDS', 0.05):
                with contextlib.redirect_stdout(io.StringIO()) as messages:
                    result=local.checked_command([sys.executable, '-c',
                        'import time;print("SENSITIVE_PROVIDER_CONTENT");time.sleep(0.21)'],
                        label='Q04 download fixture', cwd=Path(tmp))
                self.assertEqual(result.returncode,0)
                output=messages.getvalue()
                self.assertIn('Q04 download fixture: still running', output)
                self.assertNotIn('SENSITIVE_PROVIDER_CONTENT', output)

    def test_failing_command_keeps_safe_stage_and_exit_code(self):
        with self.assertRaisesRegex(local.LocalBuildError, r'Go unit tests failed \(exit 9\)'):
            local.checked_command([sys.executable, '-c', 'import sys;sys.exit(9)'],
                                  label='Go unit tests')

    def test_evidence_only_never_requires_go(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            evidence, policy, lock, native = fixture.staged_fixture(root)
            with patch.object(local,'selected_go') as toolchain, \
                 patch.object(local.q05, 'evidence_inventory',
                              return_value={'selection': {'run_id': local.RUN_ID}}):
                with contextlib.redirect_stdout(io.StringIO()):
                    result=local.build(provider='bclone', existing_evidence=evidence,
                                       verify_only=True)
                toolchain.assert_not_called()
                self.assertEqual(result['final_seal'],'NOT_ISSUED')

    def test_local_1271_full_candidate_receipt_matches_built_binary(self):
        """End-to-end local candidate uses verified Q04 provider and records 1.27.1."""
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence, policy, lock, fixture_native = fixture.staged_fixture(root)
            artifact_dir = root/'local-candidates'

            def fake_command(argv, **kwargs):
                if len(argv) > 1 and argv[1] == 'build':
                    shutil.copyfile(fixture_native, argv[argv.index('-o') + 1])
                if len(argv) > 2 and argv[1:3] == ['version', '-m']:
                    return subprocess.CompletedProcess(argv, 0, stdout=(
                        b'file: go1.27.1\n  build GOOS=android\n'
                        b'  build GOARCH=arm64\n  build CGO_ENABLED=0\n'))
                return subprocess.CompletedProcess(argv, 0, stdout=b'')

            actual_inventory = q05.evidence_inventory
            actual_assemble = q05.assemble
            with patch.object(local.q05, 'LOCK', lock), \
                 patch.object(local, 'evidence_root', return_value=evidence), \
                 patch.object(q05, 'evidence_inventory', side_effect=lambda source, *args, **kwargs: actual_inventory(source, policy, lock)), \
                 patch.object(q05, 'assemble', side_effect=lambda source, native, output, *, providers: actual_assemble(source,native,output,policy,lock,providers=providers)), \
                 patch.object(local, 'selected_go', return_value=('1.27.1', {
                      'GOTOOLCHAIN':'local','GOWORK':'off','CGO_ENABLED':'0'})), \
                 patch.object(local, 'checked_command', side_effect=fake_command), \
                 patch.object(local, 'verify_webui'):
                with contextlib.redirect_stdout(io.StringIO()):
                    report = local.build(provider='bclone', existing_evidence=evidence,
                                         output_parent=artifact_dir)
            out=Path(report['local_output'])
            sidecar=json.loads((out/'candidate-evidence.json').read_bytes())
            self.assertEqual(sidecar['toolchain'],'go1.27.1')
            self.assertEqual(sidecar['selected_ci_toolchain'],'go1.27.2')
            self.assertFalse(sidecar['local_go_matches_ci_pin'])
            self.assertEqual(sidecar['build_kind'],'LOCAL_DEVELOPMENT_UNQUALIFIED')
            self.assertEqual(sidecar['final_seal'],'NOT_ISSUED')
            self.assertFalse(sidecar['independent_attestation'])
            self.assertEqual(len(list(out.glob('*.zip'))),1)
            self.assertEqual(q05.release.verify_release(next(out.glob('*.zip')))['qualification'],
                             'CANDIDATE_ONLY_NOT_SEALED')

    def test_webui_syntax_is_compilation_gate(self):
        local.verify_webui()

if __name__ == '__main__': unittest.main()
