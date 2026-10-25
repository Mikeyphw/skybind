"""Fail-closed source contracts for Android 16 config review consent.

Static tests cannot prove device visibility; real instrumentation is still required.
"""
import unittest
from unittest.mock import patch
from scripts.dev.android import native06_source_gate as gate

EDITOR = 'android-app/app/src/main/java/io/github/mikeyphw/skybind/ui/MountConfigEditor.kt'
UI_TEST = 'android-app/app/src/androidTest/java/io/github/mikeyphw/skybind/NativeUiTest.kt'


class ConfigConsentContract(unittest.TestCase):
    def test_source_gate_passes(self):
        self.assertEqual(gate.check()['status'], 'PASS_NATIVE06_ACCEPTANCE_SOURCE_ONLY')

    def corrupt(self, path, old, new, expected):
        original = gate.source
        def tampered(filename):
            data = original(filename)
            if filename == path:
                self.assertIn(old, data)
                return data.replace(old, new, 1)
            return data
        with patch.object(gate, 'source', side_effect=tampered):
            with self.assertRaisesRegex(RuntimeError, expected):
                gate.check()

    def test_cannot_remove_accessible_consent_tag(self):
        self.corrupt(EDITOR, '.testTag("config-consent")', '.testTag("wrong")',
                     'NATIVE06_CONFIG_REVIEW_CONSENT_ACCESSIBILITY_OR_GATE_INVALID')

    def test_cannot_remove_checkbox_semantics_role(self):
        self.corrupt(EDITOR, 'role = Role.Checkbox', 'role = Role.Switch',
                     'NATIVE06_CONFIG_REVIEW_CONSENT_ACCESSIBILITY_OR_GATE_INVALID')

    def test_cannot_make_inner_checkbox_second_click_target(self):
        self.corrupt(EDITOR, 'Checkbox(checked = consent, onCheckedChange = null)',
                     'Checkbox(checked = consent, onCheckedChange = { consent = it })',
                     'NATIVE06_CONFIG_REVIEW_CONSENT_ACCESSIBILITY_OR_GATE_INVALID')

    def test_cannot_enable_apply_without_consent(self):
        self.corrupt(EDITOR, 'enabled = !busy && consent', 'enabled = !busy',
                     'NATIVE06_CONFIG_REVIEW_CONSENT_ACCESSIBILITY_OR_GATE_INVALID')

    def test_cannot_keep_consent_across_preview_id(self):
        self.corrupt(EDITOR, 'remember(preview?.id)', 'remember(mode)',
                     'NATIVE06_CONFIG_REVIEW_CONSENT_ACCESSIBILITY_OR_GATE_INVALID')

    def test_checkbox_not_available_without_preview(self):
        self.corrupt(EDITOR, 'if (step == 3 && preview != null)',
                     'if (step == 3)',
                     'NATIVE06_CONFIG_REVIEW_CONSENT_ACCESSIBILITY_OR_GATE_INVALID')

    def test_touch_cannot_be_removed_from_device_test(self):
        self.corrupt(UI_TEST, 'compose.onNodeWithTag("config-consent").assertIsOn()',
                     'compose.onNodeWithTag("config-consent").assertExists()',
                     'NATIVE06_CONFIG_CONSENT_TEST_COVERAGE_MISSING')

    def test_disabled_apply_assertion_mandatory(self):
        self.corrupt(UI_TEST, 'compose.onNodeWithTag("config-apply").assertIsNotEnabled()',
                     'compose.onNodeWithTag("config-apply").assertExists()',
                     'NATIVE06_CONFIG_CONSENT_TEST_COVERAGE_MISSING')


if __name__ == '__main__':
    unittest.main()
