"""Source contracts for Android 16 signer disclosure after the More page expands.

The device fixture's dynamic Compose semantics remains the release authority;
these tests only guard the source layout and callback flow.
"""
import unittest
from unittest.mock import patch
from scripts.dev.android import native06_source_gate as gate

APP = 'android-app/app/src/main/java/io/github/mikeyphw/skybind/ui/SkybindApp.kt'
POLISH = 'android-app/app/src/androidTest/java/io/github/mikeyphw/skybind/NativePolishUiTest.kt'

class SignerDisclosureDialogContract(unittest.TestCase):
    def test_current_source_gate(self):
        self.assertEqual(gate.check()['status'], 'PASS_NATIVE06_ACCEPTANCE_SOURCE_ONLY')

    def assert_rejected(self, path, old, replacement):
        real = gate.source
        def swapped(p):
            original = real(p)
            if p == path:
                self.assertIn(old, original)
                return original.replace(old, replacement, 1)
            return original
        with patch.object(gate, 'source', side_effect=swapped):
            with self.assertRaisesRegex(RuntimeError, 'NATIVE06_SIGNER_DISCLOSURE_DIALOG_CONTRACT_INVALID'):
                gate.check()

    def test_cannot_revert_to_inline_offscreen_card(self):
        self.assert_rejected(APP, 'if (showSigner) {', 'if (showSigner) InfoPanel(')

    def test_requires_production_dialog(self):
        self.assert_rejected(APP, 'modifier = Modifier.testTag("about-signer-dialog")',
                             'modifier = Modifier.testTag("not-a-dialog")')

    def test_requires_fingerprint_value_not_placeholder(self):
        self.assert_rejected(APP, 'NativePresentation.signer(context)', '"UNKNOWN"')

    def test_cannot_disable_dismissal(self):
        self.assert_rejected(APP, 'onDismissRequest = { showSigner = false }',
                             'onDismissRequest = { }')

    def test_cannot_remove_close_control(self):
        self.assert_rejected(APP, 'modifier = Modifier.testTag("about-signer-close")',
                             'modifier = Modifier.testTag("removed-close")')

    def test_test_must_assert_dialog_open(self):
        self.assert_rejected(POLISH, 'onNodeWithTag("about-signer-dialog", useUnmergedTree = true).assertExists()',
                             'onNodeWithTag("about-signer-dialog", useUnmergedTree = true).assertDoesNotExist()')

    def test_test_must_click_dismiss(self):
        self.assert_rejected(POLISH, '.assertIsDisplayed().performClick()',
                             '.assertIsDisplayed().assertExists()')

    def test_test_must_examine_fingerprint(self):
        self.assert_rejected(POLISH, '.assertTextEquals(expectedSigner).assertIsDisplayed()',
                             '.assertExists()')

    def test_test_must_probe_unmerged_semantics(self):
        self.assert_rejected(POLISH, 'compose.onAllNodesWithTag(tag, useUnmergedTree = true)',
                             'compose.onAllNodesWithTag(tag)')

    def test_test_must_report_bounded_tag_counts(self):
        self.assert_rejected(POLISH, '"NATIVE06_SIGNER_SEMANTICS_V1 phase=$phase "',
                             '"SIGNER_PROBE_DISABLED "')

    def test_test_must_keep_sha256_identity_check(self):
        self.assert_rejected(POLISH, 'Regex("[0-9a-f]{64}").matches(expectedSigner)',
                             'true')

    def test_test_must_wait_for_dialog_composition(self):
        self.assert_rejected(POLISH, 'compose.waitForIdle()\n        val afterClick = signerSemantics("after_click")',
                             'val afterClick = signerSemantics("after_click")')

    def test_test_must_check_post_close_absence(self):
        self.assert_rejected(POLISH,
                             'onNodeWithTag("about-signer-close", useUnmergedTree = true).assertDoesNotExist()',
                             'onNodeWithTag("about-signer-close", useUnmergedTree = true).assertExists()')

    def test_signer_presentation_import_must_be_explicit(self):
        real = gate.source
        def missing_import(path):
            s = real(path)
            if path == POLISH:
                self.assertIn('import io.github.mikeyphw.skybind.ui.NativePresentation', s)
                return s.replace('import io.github.mikeyphw.skybind.ui.NativePresentation', '', 1)
            return s
        with patch.object(gate, 'source', side_effect=missing_import):
            with self.assertRaisesRegex(RuntimeError, 'NATIVE06_SIGNER_PRESENTATION_IMPORT_INVALID'):
                gate.check()

    def test_signer_presentation_wrong_package_must_fail(self):
        real = gate.source
        def wrong_import(path):
            s = real(path)
            if path == POLISH:
                return s.replace('import io.github.mikeyphw.skybind.ui.NativePresentation',
                                 'import io.github.mikeyphw.skybind.NativePresentation', 1)
            return s
        with patch.object(gate, 'source', side_effect=wrong_import):
            with self.assertRaisesRegex(RuntimeError, 'NATIVE06_SIGNER_PRESENTATION_IMPORT_INVALID'):
                gate.check()

    def test_dialog_stays_production_unchanged_in_this_diagnostic_change(self):
        self.assertIn('NativePresentation.signer(context)', gate.source(APP))

if __name__ == '__main__':
    unittest.main()
