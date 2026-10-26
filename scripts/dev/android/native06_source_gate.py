#!/usr/bin/env python3
"""NATIVE-06 safety/source shape gate. Not an Android compile or device receipt."""
from pathlib import Path
import json
import xml.etree.ElementTree as ET
import re
ROOT = Path(__file__).resolve().parents[3]

def source(path):
    p = ROOT / path
    if p.is_symlink() or not p.is_file():
        raise RuntimeError('REQUIRED_NATIVE06_SOURCE_MISSING:' + path)
    return p.read_text()

def check():
    runner = source('scripts/dev/android/native06_personal_acceptance.py')
    live = source('android-app/app/src/androidTest/java/io/github/mikeyphw/skybind/NativePersonalLiveTest.kt')
    for code in ('EXACT_COMMITTED_APK_SOURCE_REQUIRED', 'HOSTED_WORKFLOW_SOURCE_MISMATCH',
                 'EXACT_SIGNED_PERSONAL_APP_AND_TEST_NOT_INSTALLED',
                 'INSTALLED_NATIVE_DAEMON_BINARY_MISMATCH_OR_UNREADABLE',
                 'INSTRUMENTATION_FAILED_OR_SKIPPED', 'RECEIPT_NOT_FROM_OPERATOR_STATE_DIRECTORY',
                 'SAME_SOURCE_INSTALLED_MODULE_EVIDENCE_MISSING',
                 'EXPLICIT_ALL_OWNER_APPROVAL_FLAGS_REQUIRED',
                 'APPROVAL_ARTIFACT_DRIFT', 'REQUIRED_DEVICE_LANE_MISSING',
                 'READONLY_MUST_NOT_HAVE_MUTATION_CONSENT',
                 'MOUNT_FIXTURE_PATH_ALREADY_PRESENT_OR_UNKNOWN',
                 'MOUNT_FIXTURE_CLEANUP_FAILED_INSPECT_DEVICE',
                 'ACTIVE_SKYBIND_DAEMON_BINARY_STALE_OR_UNREADABLE',
                 'ANDROID_36_QUALIFICATION_TARGET_REQUIRED'):
        if code not in runner:
            raise RuntimeError('MISSING_NATIVE06_FAIL_CLOSED_GUARD:' + code)
    for code in ('automaticForegroundRootNoManualConnect', 'mountsMatchAuthoritativeDaemon',
                 'disposableMountStartRestartStopReconcile',
                 'NATIVE_PERSONAL_LIFECYCLE_NOT_AUTHORIZED',
                 'global reconcile requires isolated inactive registry',
                 'root.previewMount("start", name)', 'root.previewMount("restart", name)',
                 'root.previewMount("stop", name)', 'root.previewMount("reconcile", "")',
                 'root.previewConfig("delete", name, null)',
                 '"skybind.native.personal.mountpoint"',
                 'mountpoint = mountpoint,'):
        if code not in live:
            raise RuntimeError('MISSING_NATIVE06_DEVICE_CONTRACT:' + code)
    # Android instrumentation runs inside io.github.mikeyphw.skybind, NOT
    # io.github.mikeyphw.skybind.test. A host declared in the test APK fails
    # ActivityScenario with "resolved to different process" on real devices.
    host_source = source('android-app/app/src/androidTest/AndroidManifest.xml')
    ns = '{http://schemas.android.com/apk/res/android}'
    try:
        host_root = ET.fromstring(host_source)
        prod_root = ET.fromstring(source('android-app/app/src/main/AndroidManifest.xml'))
    except ET.ParseError as exc:
        raise RuntimeError('NATIVE06_COMPOSE_TEST_MANIFEST_MALFORMED') from exc
    if host_root.tag != 'manifest' or list(host_root):
        raise RuntimeError('NATIVE06_COMPOSE_FOREIGN_PROCESS_HOST_OR_PERMISSIONS')
    activities = prod_root.findall('./application/activity')
    if any(a.get(ns + 'name') == 'androidx.activity.ComponentActivity' for a in activities):
        raise RuntimeError('NATIVE06_COMPOSE_TEST_HOST_IN_PRODUCTION')
    main = [a for a in activities if a.get(ns + 'name') == '.MainActivity']
    if len(main) != 1 or main[0].get(ns + 'exported') != 'true':
        raise RuntimeError('NATIVE06_COMPOSE_TARGET_MAINACTIVITY_INVALID')
    launcher = main[0].find('intent-filter')
    if launcher is None or not (launcher.find("action[@" + ns + "name='android.intent.action.MAIN']") is not None and
                              launcher.find("category[@" + ns + "name='android.intent.category.LAUNCHER']") is not None):
        raise RuntimeError('NATIVE06_COMPOSE_TARGET_MAINACTIVITY_INVALID')
    activity = source('android-app/app/src/main/java/io/github/mikeyphw/skybind/MainActivity.kt')
    if 'class MainActivity : ComponentActivity()' not in activity:
        raise RuntimeError('NATIVE06_COMPOSE_TARGET_MAINACTIVITY_INVALID')
    for test in ('NativeUiTest.kt', 'NativePolishUiTest.kt', 'RemoteBrowserTest.kt'):
        ui = source('android-app/app/src/androidTest/java/io/github/mikeyphw/skybind/' + test)
        required = ('createAndroidComposeRule<MainActivity>()',
                    'private fun fixtureContent(content: @Composable () -> Unit)',
                    'val activity = compose.activity',
                    'compose.runOnUiThread { activity.setContent(content = content) }',
                    'compose.waitForIdle()',
                    'fixtureContent {')
        if any(v not in ui for v in required) or 'createComposeRule()' in ui or re.search(r'^\s*compose\.setContent\s*\{', ui, re.M):
            raise RuntimeError('NATIVE06_COMPOSE_TARGET_PROCESS_RULE_INVALID:' + test)
    # On API 36 with larger font scaling, Material3 Dialog's scroll region
    # may clip the review checkbox from the merged semantics tree while the
    # action footer remains present. Consent must be an independent clickable
    # semantics node outside the bounded review-details scroller.
    editor = source('android-app/app/src/main/java/io/github/mikeyphw/skybind/ui/MountConfigEditor.kt')
    config_test = source('android-app/app/src/androidTest/java/io/github/mikeyphw/skybind/NativeUiTest.kt')
    review_scroll = editor.find('Column(Modifier.heightIn(max = 480.dp).verticalScroll')
    review_footer = editor.find('if (step == 3 && preview != null)')
    action_footer = editor.find('modifier = Modifier.testTag("config-apply")')
    consent_tag = editor.find('.testTag("config-consent")')
    if (min(review_scroll, review_footer, consent_tag, action_footer) < 0 or
            not (review_scroll < review_footer < consent_tag < action_footer) or
            'toggleable(value = consent, role = Role.Checkbox,' not in editor or
            'Checkbox(checked = consent, onCheckedChange = null)' not in editor or
            'var consent by remember(preview?.id) { mutableStateOf(false) }' not in editor or
            'enabled = !busy && consent' not in editor or
            'onClick = onApply' not in editor or
            'if (step == 3 && preview != null)' not in editor):
        raise RuntimeError('NATIVE06_CONFIG_REVIEW_CONSENT_ACCESSIBILITY_OR_GATE_INVALID')
    if ('compose.onNodeWithTag("config-consent").assertIsOff()' not in config_test or
            'compose.onNodeWithTag("config-consent").assertIsOn()' not in config_test or
            'compose.onNodeWithTag("config-apply").assertIsNotEnabled()' not in config_test or
            'compose.runOnIdle { assertEquals(1, applies) }' not in config_test):
        raise RuntimeError('NATIVE06_CONFIG_CONSENT_TEST_COVERAGE_MISSING')
    # A formerly inline signer card after the More page's long scrolling
    # content became undiscoverable on Android 16. Require a separate dialog
    # with an explicit, independently testable dismiss action. This test-only
    # source guard never substitutes for an instrumented device result.
    app_ui = source('android-app/app/src/main/java/io/github/mikeyphw/skybind/ui/SkybindApp.kt')
    polish = source('android-app/app/src/androidTest/java/io/github/mikeyphw/skybind/NativePolishUiTest.kt')
    signer_required = (
        'if (showSigner) {',
        'AlertDialog(',
        'onDismissRequest = { showSigner = false }',
        'modifier = Modifier.testTag("about-signer-dialog")',
        'modifier = Modifier.testTag("about-signer-sha256")',
        'modifier = Modifier.testTag("about-signer-close")',
        'NativePresentation.signer(context)',
    )
    # Query both semantics trees without dumping text or fingerprint values.
    # Keep the full unmerged-dialog, SHA-256 and close/dismiss assertions;
    # a missing dialog must remain BLOCKED, not silently be counted as PASS.
    signer_test_required = (
        'onNodeWithTag("about-signer-dialog").assertDoesNotExist()',
        'onNodeWithTag("about-signer-dialog", useUnmergedTree = true).assertDoesNotExist()',
        'onNodeWithTag("about-show-signer").performClick()',
        'compose.waitForIdle()\n        val afterClick = signerSemantics("after_click")',
        'onNodeWithTag("about-signer-dialog", useUnmergedTree = true).assertExists()',
        'onNodeWithTag("about-signer-sha256", useUnmergedTree = true)',
        '.assertTextEquals(expectedSigner).assertIsDisplayed()',
        'onNodeWithTag("about-signer-close", useUnmergedTree = true)',
        '.assertIsDisplayed().performClick()',
        'onNodeWithTag("about-signer-dialog", useUnmergedTree = true).assertDoesNotExist()',
        'onNodeWithTag("about-signer-sha256", useUnmergedTree = true).assertDoesNotExist()',
        'onNodeWithTag("about-signer-close", useUnmergedTree = true).assertDoesNotExist()',
        'Regex("[0-9a-f]{64}").matches(expectedSigner)',
        'throw AssertionError(afterClick + " (bounded signer-only semantics)", failure)',
        'val merged = compose.onAllNodesWithTag(tag).fetchSemanticsNodes().size',
        'compose.onAllNodesWithTag(tag, useUnmergedTree = true)',
        '"NATIVE06_SIGNER_SEMANTICS_V1 phase=$phase "',
    )
    if any(v not in app_ui for v in signer_required) or \
            'if (showSigner) InfoPanel(' in app_ui or \
            any(v not in polish for v in signer_test_required):
        raise RuntimeError('NATIVE06_SIGNER_DISCLOSURE_DIALOG_CONTRACT_INVALID')
    gradle = source('android-app/app/build.gradle.kts')
    if 'testBuildType = if (personalRequested) "personal" else "debug"' not in gradle or \
            'personalImplementation("androidx.compose.ui:ui-test-manifest")' in gradle:
        raise RuntimeError('NATIVE06_COMPOSE_PRODUCTION_TEST_HOST_UNSAFE')
    if 'onNodeWithTag("connect-readonly").performClick()' in live:
        raise RuntimeError('AUTO_ROOT_TEST_MUST_NOT_USE_MANUAL_CONNECT')
    if any(x in runner for x in ("adb(serial, 'uninstall'", "adb(serial, 'install'", "'pm', 'clear'")):
        raise RuntimeError('NATIVE06_MUST_NOT_INSTALL_OR_CLEAR_DEVICE')
    return {'status':'PASS_NATIVE06_ACCEPTANCE_SOURCE_ONLY', 'android_built':False,
            'device_qualified':False, 'release_qualified':False}

if __name__ == '__main__':
    print(json.dumps(check(),sort_keys=True))
