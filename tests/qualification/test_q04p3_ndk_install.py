"""SB-Q04P3: fix sdkmanager SIGPIPE false failures while remaining fail-closed."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / '.github/workflows/skybind-provider-reproducibility.yml'
PIN = '28.2.13676358'


def sdkmanager_install_block() -> str:
    content = WORKFLOW.read_text(encoding='utf-8')
    marker = '      - name: Install pinned NDK (no mutable runtime)\n'
    if content.count(marker) != 1:
        raise AssertionError('expected exactly one install step')
    region = content.split(marker, 1)[1].split('      - name:', 1)[0]
    if '        run: |\n' not in region:
        raise AssertionError('missing workflow installer Bash block')
    commands = region.split('        run: |\n', 1)[1]
    return textwrap.dedent(commands).strip() + '\n'


class NDKInstallContractTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.tmp = Path(td.name)
        self.sdk = self.tmp / 'android-sdk'
        sdkman = self.sdk / 'cmdline-tools/latest/bin/sdkmanager'
        sdkman.parent.mkdir(parents=True)
        sdkman.write_text('''#!/usr/bin/env bash
set -euo pipefail
[[ "${1-}" == "ndk;28.2.13676358" ]] || exit 49
case "${MOCK_SDK_RESULT:-good}" in
  fail) echo 'sdkmanager deliberately failed' >&2; exit 23;;
  missing) exit 0;;
esac
ndk="$ANDROID_HOME/ndk/28.2.13676358"
mkdir -p "$ndk/toolchains/llvm/prebuilt/linux-x86_64/bin"
if [[ "${MOCK_SDK_RESULT:-good}" == 'bad_revision' ]]; then
  echo 'Pkg.Revision = 27.0.0' > "$ndk/source.properties"
else
  echo 'Pkg.Revision = 28.2.13676358' > "$ndk/source.properties"
fi
if [[ "${MOCK_SDK_RESULT:-good}" != 'missing_compiler' ]]; then
  c="$ndk/toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android21-clang"
  printf '#!/bin/sh\\nexit 0\\n' > "$c"
  chmod +x "$c"
fi
''')
        sdkman.chmod(0o755)
        self.fakebin = self.tmp / 'fakebin'
        self.fakebin.mkdir()
        # Deterministic surrogate for 'yes' failing with EPIPE after sdkmanager
        # consumes the license input; the installer must remain authoritative.
        mockyes = self.fakebin / 'yes'
        mockyes.write_text('#!/bin/sh\nexit 97\n')
        mockyes.chmod(0o755)

    def run_block(self, mode: str = 'good', *, real_yes: bool = False, appendix: str = ''):
        env = os.environ.copy()
        env['ANDROID_HOME'] = str(self.sdk)
        env['MOCK_SDK_RESULT'] = mode
        env['PATH'] = ((str(self.fakebin) + os.pathsep) if not real_yes else '') + env['PATH']
        return subprocess.run(['bash', '--noprofile', '--norc', '-e', '-o', 'pipefail', '-c',
                               sdkmanager_install_block() + appendix], cwd=self.tmp,
                              env=env, text=True, capture_output=True, timeout=15)

    def test_mock_yes_nonzero_does_not_mask_successful_sdkmanager(self):
        result = self.run_block()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.sdk / f'ndk/{PIN}/source.properties').is_file())

    def test_real_yes_sigpipe_is_nonfatal_after_successful_installer(self):
        result = self.run_block(real_yes=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('Broken pipe', result.stderr)

    def test_sdkmanager_failure_is_fatal_even_when_yes_also_fails(self):
        result = self.run_block('fail')
        self.assertEqual(result.returncode, 23)
        self.assertIn('sdkmanager deliberately failed', result.stderr)

    def test_missing_ndk_payload_is_fatal(self):
        self.assertNotEqual(self.run_block('missing').returncode, 0)

    def test_wrong_ndk_revision_is_fatal(self):
        self.assertNotEqual(self.run_block('bad_revision').returncode, 0)

    def test_missing_api21_compiler_is_fatal(self):
        self.assertNotEqual(self.run_block('missing_compiler').returncode, 0)

    def test_pipefail_is_restored_and_subsequent_failure_is_fatal(self):
        result = self.run_block(appendix='false | true\n')
        self.assertNotEqual(result.returncode, 0)

    def test_workflow_pins_and_release_authority_remain_unchanged(self):
        content = WORKFLOW.read_text(encoding='utf-8')
        block = sdkmanager_install_block()
        self.assertEqual(block.count('set +o pipefail'), 1)
        self.assertEqual(block.count('set -o pipefail'), 1)
        self.assertLess(block.index('set +o pipefail'), block.index('yes 2>/dev/null |'))
        self.assertLess(block.index('yes 2>/dev/null |'), block.index('set -o pipefail'))
        self.assertIn("'ndk;28.2.13676358'", block)
        self.assertIn('aarch64-linux-android21-clang', block)
        self.assertIn('Pkg\\.Revision', block)
        self.assertIn('lane: [A, B]', content)
        self.assertIn('pin_selection.py verify', content)
        self.assertIn('source_build.py pins', content)
        self.assertNotIn('schedule:', content)
        self.assertNotIn('release create', content)
        self.assertTrue('compare-independent-builds:' in content)
        lock = json.loads((ROOT / 'scripts/dev/runtime/source.lock.json').read_text())
        self.assertEqual(lock['bclone']['ndk_revision'], PIN)
        self.assertEqual(lock['bclone']['go_version'], '1.27.2')
        self.assertEqual(lock['newfuture']['archive_sha256'], '04ebfcc8c21c9583b7d4c723e2e69c1d3bbbd24432f6728ffbc2947e5282aa43')
        self.assertIn('q04p3-ndk-install-contract', (ROOT / '.devtool.toml').read_text())
        self.assertIn('check_q04p3_ndk_install.sh', (ROOT / '.github/workflows/skybind-source.yml').read_text())


if __name__ == '__main__':
    unittest.main()
