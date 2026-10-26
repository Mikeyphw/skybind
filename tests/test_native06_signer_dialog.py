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
        self.assert_rejected(POLISH, 'onNodeWithTag("about-signer-dialog").assertExists()',
                             'onNodeWithTag("about-signer-dialog").assertDoesNotExist()')

    def test_test_must_click_dismiss(self):
        self.assert_rejected(POLISH, 'onNodeWithTag("about-signer-close").performClick()',
                             'onNodeWithTag("about-signer-close").assertExists()')

    def test_test_must_examine_fingerprint(self):
        self.assert_rejected(POLISH, 'onNodeWithTag("about-signer-sha256").assertExists()',
                             'onNodeWithTag("about-signer-sha256").assertDoesNotExist()')

if __name__ == '__main__':
    unittest.main()
