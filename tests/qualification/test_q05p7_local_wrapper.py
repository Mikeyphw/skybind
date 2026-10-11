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

    def test_selected_go_version_is_strict(self):
        with patch.object(local, 'checked_command', return_value=subprocess.CompletedProcess([], 0, stdout=b'go version go1.27.1 android/arm64\n')):
            with self.assertRaisesRegex(local.LocalBuildError, 'Go 1.27.2'):
                local.selected_go('go')
        with patch.object(local, 'checked_command', return_value=subprocess.CompletedProcess([], 0, stdout=b'go version go1.27.2 android/arm64\n')):
            version, env = local.selected_go('go')
            self.assertEqual(version, '1.27.2')
            self.assertEqual(env['GOTOOLCHAIN'], 'local')
            self.assertEqual(env['CGO_ENABLED'], '0')

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

    def test_webui_syntax_is_compilation_gate(self):
        local.verify_webui()

if __name__ == '__main__': unittest.main()
