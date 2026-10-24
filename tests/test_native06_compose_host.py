"""Source-only regressions for NATIVE-06 Compose instrumented activity isolation.

Not evidence that the hosted APK or real Android device test has passed.
"""
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
from pathlib import Path
from scripts.dev.android import native06_source_gate as gate

MANIFEST = 'android-app/app/src/androidTest/AndroidManifest.xml'
PROD = 'android-app/app/src/main/AndroidManifest.xml'

class ComposeTestHostContract(unittest.TestCase):
    def test_source_gate_accepts_instrumentation_only_host(self):
        self.assertEqual(gate.check()['status'], 'PASS_NATIVE06_ACCEPTANCE_SOURCE_ONLY')

    def _expect_block(self, replace, error):
        real = gate.source
        def modified(path):
            content = real(path)
            return replace(content) if path == MANIFEST else content
        with patch.object(gate, 'source', side_effect=modified):
            with self.assertRaisesRegex(RuntimeError, error):
                gate.check()

    def test_absent_host_is_denied(self):
        self._expect_block(lambda s: s.replace('androidx.activity.ComponentActivity',
                                                 'androidx.activity.OtherActivity'), 'HOST_UNSAFE_OR_ABSENT')

    def test_non_exported_host_is_denied(self):
        self._expect_block(lambda s: s.replace('android:exported="true"',
                                                 'android:exported="false"'), 'HOST_UNSAFE_OR_ABSENT')

    def test_extra_launcher_is_denied(self):
        self._expect_block(lambda s: s.replace(' />', '><intent-filter /></activity>', 1),
                           'HOST_UNSAFE_OR_ABSENT')

    def test_malformed_manifest_is_denied(self):
        self._expect_block(lambda s: s.replace('</manifest>', ''), 'MANIFEST_MALFORMED')

    def test_permissions_are_not_added(self):
        self._expect_block(lambda s: s.replace('<application>',
            '<uses-permission android:name="android.permission.CAMERA" />\n    <application>'),
            'HOST_ADDS_PERMISSION')

    def test_production_host_is_rejected(self):
        original=gate.source
        def altered(path):
            content=original(path)
            if path == PROD:
                return content.replace('</application>',
                    '<activity android:name="androidx.activity.ComponentActivity" />\n</application>')
            return content
        with patch.object(gate, 'source', side_effect=altered):
            with self.assertRaisesRegex(RuntimeError, 'HOST_IN_PRODUCTION'):
                gate.check()

    def test_build_type_is_not_changed_to_debug(self):
        root=Path(gate.ROOT)
        gradle=(root/'android-app/app/build.gradle.kts').read_text()
        self.assertIn('testBuildType = if (personalRequested) "personal" else "debug"', gradle)
        self.assertIn('debugImplementation("androidx.compose.ui:ui-test-manifest")', gradle)
        self.assertNotIn('personalImplementation("androidx.compose.ui:ui-test-manifest")', gradle)

if __name__ == '__main__':
    unittest.main()
