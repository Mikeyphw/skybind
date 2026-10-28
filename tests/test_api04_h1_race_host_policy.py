"""Fail-closed tests for the P3-H1 platform-specific race qualification gate."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

GATE = Path(__file__).resolve().parents[1] / 'scripts/devtool/api04_h1_race_gate.sh'


class GoRaceHostQualification(unittest.TestCase):
    def run_gate(self, *, host_os, host_arch, target_os=None, target_arch=None, fail_test=False):
        with tempfile.TemporaryDirectory(prefix='skybind-race-policy-') as directory:
            root = Path(directory)
            fake = root / 'go'
            fake.write_text('''''''''#!/bin/sh
set -eu
if [ "$1" = env ]; then
  case "$2" in
    GOOS) printf '%s\n' "$MOCK_TARGET_OS" ;;
    GOARCH) printf '%s\n' "$MOCK_TARGET_ARCH" ;;
    GOHOSTOS) printf '%s\n' "$MOCK_HOST_OS" ;;
    GOHOSTARCH) printf '%s\n' "$MOCK_HOST_ARCH" ;;
    *) exit 14 ;;
  esac
  exit 0
fi
printf '%s\n' "$*" >> "$MOCK_GO_CALLS"
if [ "${MOCK_TEST_FAIL:-0}" = 1 ]; then exit 23; fi
''''''''' , encoding='utf-8')
            fake.chmod(0o755)
            calls = root / 'calls'
            env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ.get('PATH', ''),
                       MOCK_HOST_OS=host_os, MOCK_HOST_ARCH=host_arch,
                       MOCK_TARGET_OS=target_os or host_os, MOCK_TARGET_ARCH=target_arch or host_arch,
                       MOCK_TEST_FAIL='1' if fail_test else '0', MOCK_GO_CALLS=str(calls))
            result = subprocess.run(['sh', str(GATE)], env=env, cwd=GATE.parents[2],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, timeout=15, check=False)
            return result, calls.read_text().splitlines() if calls.exists() else []

    def test_android_arm64_repeats_uncached_without_race(self):
        result, calls = self.run_gate(host_os='android', host_arch='arm64')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 1)
        self.assertIn('test -p 2 -count=3', calls[0])
        self.assertNotIn('-race', calls[0])
        self.assertIn('RACE_GATE_DEFERRED', result.stdout)
        self.assertNotIn('RACE_DETECTOR_PASS', result.stdout)

    def test_linux_host_requires_race_detector(self):
        result, calls = self.run_gate(host_os='linux', host_arch='amd64')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 1)
        self.assertIn('test -race -count=1', calls[0])
        self.assertIn('RACE_DETECTOR_PASS', result.stdout)

    def test_darwin_arm64_requires_race_detector(self):
        result, calls = self.run_gate(host_os='darwin', host_arch='arm64')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('test -race', calls[0])

    def test_unknown_native_host_fails_closed(self):
        result, calls = self.run_gate(host_os='android', host_arch='x86')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(calls, [])
        self.assertIn('BLOCKED_API04_H1_UNQUALIFIED_RACE_PLATFORM', result.stderr)

    def test_cross_target_is_never_skipped(self):
        result, calls = self.run_gate(host_os='linux', host_arch='amd64', target_os='android', target_arch='arm64')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(calls, [])
        self.assertIn('BLOCKED_API04_H1_NON_NATIVE_TEST_TARGET', result.stderr)

    def test_android_native_test_failure_remains_failure(self):
        result, calls = self.run_gate(host_os='android', host_arch='arm64', fail_test=True)
        self.assertEqual(result.returncode, 23)
        self.assertEqual(len(calls), 1)
        self.assertNotIn('REPEATED_TESTS_PASS', result.stdout)

    def test_supported_host_race_failure_remains_failure(self):
        result, calls = self.run_gate(host_os='linux', host_arch='arm64', fail_test=True)
        self.assertEqual(result.returncode, 23)
        self.assertIn('test -race', calls[0])
        self.assertNotIn('RACE_DETECTOR_PASS', result.stdout)


if __name__ == '__main__':
    unittest.main()
