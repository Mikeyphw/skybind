"""Source-only negative contracts for correct-process Compose instrumentation.

Real Android execution remains a separate, mandatory NATIVE-06 gate.
"""
import unittest
from unittest.mock import patch
from scripts.dev.android import native06_source_gate as gate

TEST_MANIFEST = 'android-app/app/src/androidTest/AndroidManifest.xml'
PROD_MANIFEST = 'android-app/app/src/main/AndroidManifest.xml'
TEST_PREFIX = 'android-app/app/src/androidTest/java/io/github/mikeyphw/skybind/'


class ComposeCorrectProcessContract(unittest.TestCase):
    def test_actual_source_satisfies_gate(self):
        self.assertEqual(gate.check()['status'], 'PASS_NATIVE06_ACCEPTANCE_SOURCE_ONLY')

    def assert_source_rejected(self, path, old, new, expected):
        real = gate.source
        def tampered(p):
            data = real(p)
            if p == path:
                self.assertIn(old, data)
                return data.replace(old, new)
            return data
        with patch.object(gate, 'source', side_effect=tampered):
            with self.assertRaisesRegex(RuntimeError, expected):
                gate.check()

    def test_test_apk_foreign_process_activity_denied(self):
        self.assert_source_rejected(TEST_MANIFEST, ' />', """>
<application><activity android:name="androidx.activity.ComponentActivity"
 android:exported="true" /></application></manifest>""",
            'NATIVE06_COMPOSE_FOREIGN_PROCESS_HOST_OR_PERMISSIONS')

    def test_test_apk_extra_permission_denied(self):
        self.assert_source_rejected(TEST_MANIFEST, ' />', """>
<uses-permission android:name="android.permission.CAMERA" /></manifest>""",
            'NATIVE06_COMPOSE_FOREIGN_PROCESS_HOST_OR_PERMISSIONS')

    def test_test_apk_malformed_denied(self):
        self.assert_source_rejected(TEST_MANIFEST, ' />', '>',
            'NATIVE06_COMPOSE_TEST_MANIFEST_MALFORMED')

    def test_production_componentactivity_denied(self):
        self.assert_source_rejected(PROD_MANIFEST, '</application>',
            '<activity android:name="androidx.activity.ComponentActivity" /></application>',
            'NATIVE06_COMPOSE_TEST_HOST_IN_PRODUCTION')

    def test_target_main_activity_missing_denied(self):
        self.assert_source_rejected(PROD_MANIFEST, 'android:name=".MainActivity"',
            'android:name=".WrongActivity"', 'NATIVE06_COMPOSE_TARGET_MAINACTIVITY_INVALID')

    def test_target_app_activity_type_must_be_componentactivity(self):
        self.assert_source_rejected(
            'android-app/app/src/main/java/io/github/mikeyphw/skybind/MainActivity.kt',
            'class MainActivity : ComponentActivity()', 'class MainActivity : Activity()',
            'NATIVE06_COMPOSE_TARGET_MAINACTIVITY_INVALID')

    def test_all_three_fixture_suites_use_same_process(self):
        for path in ('NativeUiTest.kt', 'NativePolishUiTest.kt', 'RemoteBrowserTest.kt'):
            with self.subTest(path=path):
                self.assert_source_rejected(TEST_PREFIX + path,
                    'createAndroidComposeRule<MainActivity>()', 'createComposeRule()',
                    'NATIVE06_COMPOSE_TARGET_PROCESS_RULE_INVALID')

    def test_no_direct_compose_rule_setcontent(self):
        for path in ('NativeUiTest.kt', 'NativePolishUiTest.kt', 'RemoteBrowserTest.kt'):
            with self.subTest(path=path):
                self.assert_source_rejected(TEST_PREFIX + path,
                    'fixtureContent {', 'compose.setContent {',
                    'NATIVE06_COMPOSE_TARGET_PROCESS_RULE_INVALID')

    def test_no_main_thread_activity_provider_deadlock(self):
        for path in ('NativeUiTest.kt', 'NativePolishUiTest.kt', 'RemoteBrowserTest.kt'):
            with self.subTest(path=path):
                self.assert_source_rejected(TEST_PREFIX + path,
                    'val activity = compose.activity', 'val bogus = compose.activity',
                    'NATIVE06_COMPOSE_TARGET_PROCESS_RULE_INVALID')

    def test_release_variant_cannot_gain_test_manifest_dependency(self):
        self.assert_source_rejected('android-app/app/build.gradle.kts',
            'debugImplementation("androidx.compose.ui:ui-test-manifest")',
            'debugImplementation("androidx.compose.ui:ui-test-manifest")\n    personalImplementation("androidx.compose.ui:ui-test-manifest")',
            'NATIVE06_COMPOSE_PRODUCTION_TEST_HOST_UNSAFE')


if __name__ == '__main__':
    unittest.main()
