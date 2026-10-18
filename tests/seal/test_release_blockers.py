"""Release denial regression: pins are syntax evidence, never attestation."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/dev/release-audit'))
import skybind_audit as audit


class SealDenials(unittest.TestCase):
    def _fixture(self, directory):
        """Copy only the inputs the C06 audit reads; never edit live source."""
        repo = Path(directory)
        source = ROOT / 'scripts/dev/runtime/source.lock.json'
        target = repo / 'scripts/dev/runtime/source.lock.json'
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        index = repo / 'docs/roadmap/SKYBIND_DEVTOOL_OVERLAY_INDEX.json'
        index.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / 'docs/roadmap/SKYBIND_DEVTOOL_OVERLAY_INDEX.json', index)
        return repo, target

    def _report_with(self, update):
        with tempfile.TemporaryDirectory() as tmp:
            repo, target = self._fixture(tmp)
            obj = json.loads(target.read_text())
            update(obj)
            target.write_text(json.dumps(obj))
            return audit.blocked_report(repo)

    def assert_still_blocked(self, report):
        self.assertEqual(report['status'], 'BLOCKED')
        self.assertEqual(report['final_seal'], 'NOT_ISSUED')
        self.assertEqual(report['assurance'], 'SOURCE_CANDIDATE_ONLY')
        self.assertEqual(len(report['milestone_gates']), 8)
        self.assertTrue(all(value == 'NOT_QUALIFIED' for value in report['milestone_gates'].values()))
        self.assertIn('UPSTREAM_BOTH_PROVIDERS_NOT_QUALIFIED', report['reasons'])
        self.assertIn('INDEPENDENT_DEVTOOL_GATES_NOT_PASSED', report['reasons'])

    def test_pinned_providers_still_cannot_release_without_independent_gates(self):
        """Fix stale expectation: the committed NewFuture archive is now pinned."""
        manifest = json.loads((ROOT / 'scripts/dev/runtime/source.lock.json').read_text())
        pin = manifest['newfuture']['archive_sha256']
        self.assertRegex(pin, r'^[0-9a-f]{64}$')
        report = audit.blocked_report(ROOT)
        self.assert_still_blocked(report)
        self.assertIn('ANDROID_APP_VISIBILITY_NOT_ATTESTED', report['reasons'])
        self.assertNotIn('NEWFUTURE_ARCHIVE_SHA256_UNPINNED', report['reasons'])
        self.assertNotIn('BCLONE_COMMIT_UNPINNED', report['reasons'])
        self.assertNotIn('BCLONE_TOOLCHAIN_UNPINNED', report['reasons'])

    def test_newfuture_pin_missing_or_bad_format_denied(self):
        invalid = [None, '', 'a' * 63, 'a' * 65, 'G' * 64, 'A' * 64,
                   ' ' + 'a' * 64, 7, True, [], {}]
        for value in invalid:
            with self.subTest(value=value):
                report = self._report_with(
                    lambda obj: obj['newfuture'].__setitem__('archive_sha256', value))
                self.assert_still_blocked(report)
                self.assertIn('NEWFUTURE_ARCHIVE_SHA256_UNPINNED', report['reasons'])
        report = self._report_with(lambda obj: obj['newfuture'].pop('archive_sha256'))
        self.assertIn('NEWFUTURE_ARCHIVE_SHA256_UNPINNED', report['reasons'])

    def test_bclone_commit_missing_or_malformed_denied(self):
        for value in [None, '', 'f' * 39, 'f' * 41, 'Z' * 40, 'F' * 40, 42, True, []]:
            with self.subTest(value=value):
                report = self._report_with(lambda obj: obj['bclone'].__setitem__('commit', value))
                self.assert_still_blocked(report)
                self.assertIn('BCLONE_COMMIT_UNPINNED', report['reasons'])

    def test_bclone_toolchain_missing_or_nonstring_denied(self):
        for key in ('ndk_revision', 'go_version'):
            for value in (None, '', ' ', 123, True, []):
                with self.subTest(key=key, value=value):
                    report = self._report_with(lambda obj: obj['bclone'].__setitem__(key, value))
                    self.assert_still_blocked(report)
                    self.assertIn('BCLONE_TOOLCHAIN_UNPINNED', report['reasons'])

    def test_wrong_json_structure_fails_closed_without_exception(self):
        for bad in (None, [], 5, {}, {'newfuture': None, 'bclone': {}},
                    {'newfuture': {}, 'bclone': None},
                    {'newfuture': [], 'bclone': {}},
                    {'newfuture': {}, 'bclone': []}):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as tmp:
                repo, target = self._fixture(tmp)
                target.write_text(json.dumps(bad))
                report = audit.blocked_report(repo)
                self.assert_still_blocked(report)
                self.assertIn('PROVIDER_LOCK_UNTRUSTWORTHY', report['reasons'])

    def test_unparseable_provider_lock_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, target = self._fixture(tmp)
            target.write_text('{invalid-json')
            report = audit.blocked_report(repo)
            self.assert_still_blocked(report)
            self.assertIn('PROVIDER_LOCK_UNTRUSTWORTHY', report['reasons'])

    def test_well_formed_but_unverified_pin_never_qualifies(self):
        # A 64-character hex string is only a syntax-checked pin, not proof
        # that a remote archive has this digest. Independent gates still block.
        report = self._report_with(lambda obj: obj['newfuture'].__setitem__(
            'archive_sha256', '0' * 64))
        self.assert_still_blocked(report)
        self.assertNotIn('NEWFUTURE_ARCHIVE_SHA256_UNPINNED', report['reasons'])
        self.assertIn('UPSTREAM_BOTH_PROVIDERS_NOT_QUALIFIED', report['reasons'])

    def test_invalid_repository_is_blocked_not_passed(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = audit.blocked_report(Path(tmp))
            self.assert_still_blocked(report)
            self.assertIn('PROVIDER_LOCK_UNTRUSTWORTHY', report['reasons'])
            self.assertIn('CAMPAIGN_INDEX_INVALID', report['reasons'])

    def test_cli_returns_blocked_status_and_distinct_exit_code(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / 'scripts/dev/release-audit/skybind_audit.py')],
            capture_output=True, text=True, timeout=15)
        self.assertEqual(proc.returncode, 3, proc.stderr)
        self.assert_still_blocked(json.loads(proc.stdout))


if __name__ == '__main__':
    unittest.main()
