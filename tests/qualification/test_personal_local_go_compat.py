"""Source-level local compiler exception boundary; no falsified build qualification."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/dev/integration'))
import local_build

class LocalCompilerExceptionTests(unittest.TestCase):
    def probe(self, reported: str, pin: str = '1.27.2'):
        with patch.object(local_build.q05, 'json_input', return_value={'bclone':{'go_version':pin}}), \
             patch.object(local_build, 'checked_command',
                          return_value=subprocess.CompletedProcess(['go', 'version'], 0,
                          (f'go version go{reported} android/arm64\n').encode(), b'')) as call:
            result = local_build.selected_go('go')
            call.assert_called_once()
            self.assertEqual(call.call_args.args[0], ['go', 'version'])
            self.assertEqual(call.call_args.kwargs['env']['GOTOOLCHAIN'], 'local')
            self.assertEqual(call.call_args.kwargs['env']['CGO_ENABLED'], '0')
            return result

    def test_pinned_go(self):
        self.assertEqual(self.probe('1.27.2')[0], '1.27.2')

    def test_exact_local_only_exceptions(self):
        for version in ('1.27.1','1.27.3'):
            with self.subTest(version=version):
                self.assertEqual(self.probe(version)[0],version)

    def test_reject_unreviewed_local_versions(self):
        for version in ('1.27.0', '1.27.4','1.28.0','1.26.9'):
            with self.subTest(version=version):
                with self.assertRaisesRegex(local_build.LocalBuildError,'required, found'):
                    self.probe(version)

    def test_exceptions_cannot_override_a_different_ci_pin(self):
        for version in ('1.27.1','1.27.2','1.27.3'):
            with self.subTest(version=version):
                if version == '1.27.3':
                    self.assertEqual(self.probe(version, pin='1.27.3')[0],version)
                else:
                    with self.assertRaises(local_build.LocalBuildError):
                        self.probe(version, pin='1.27.3')

    def test_true_toolchain_metadata_not_ci_equivalence(self):
        with tempfile.TemporaryDirectory() as d:
            dest=Path(d)
            report={'final_seal':'NOT_ISSUED','gate_g01':'BLOCKED',
                    'independent_attestation':False,'physical_device_tested':False,
                    'candidates':{'bclone':{'sha256':'c'*64}}}
            local_build.record_local_toolchain(dest,report,'1.27.3','1.27.2')
            saved=json.loads((dest/'candidate-evidence.json').read_text())
            self.assertEqual(saved['toolchain'],'go1.27.3')
            self.assertEqual(saved['selected_ci_toolchain'],'go1.27.2')
            self.assertIs(saved['local_go_matches_ci_pin'], False)
            self.assertEqual(saved['local_toolchain_qualification'],'NOT_ATTESTED_NOT_CI_EQUIVALENT')
            self.assertEqual(saved['final_seal'],'NOT_ISSUED')
            self.assertEqual(saved['gate_g01'],'BLOCKED')
            self.assertIs(saved['independent_attestation'],False)

    def test_unreviewed_version_rejected_for_receipts(self):
        with tempfile.TemporaryDirectory() as d:
            report={'final_seal':'NOT_ISSUED','gate_g01':'BLOCKED',
                    'independent_attestation':False,'physical_device_tested':False,
                    'candidates':{'bclone':{'sha256':'c'*64}}}
            with self.assertRaisesRegex(local_build.LocalBuildError,'unreviewed local compiler'):
                local_build.record_local_toolchain(Path(d),report,'1.27.4','1.27.2')
            self.assertFalse((Path(d)/'candidate-evidence.json').exists())

if __name__ == '__main__':
    unittest.main()
