#!/usr/bin/env python3
"""M2-L2 real UI only: strict local source gate, never build, root or device."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[3]
ANDROID = Path('android-app/app/src')
UI_TEST = ANDROID/'androidTest/java/io/github/mikeyphw/skybind/LiveUiAcceptanceTest.kt'
BROWSER_TEST = ANDROID/'androidTest/java/io/github/mikeyphw/skybind/RemoteBrowserTest.kt'
VM = ANDROID/'main/java/io/github/mikeyphw/skybind/bridge/SkybindSessionViewModel.kt'
APP = ANDROID/'main/java/io/github/mikeyphw/skybind/ui/SkybindApp.kt'
ACTIVITY = ANDROID/'main/java/io/github/mikeyphw/skybind/MainActivity.kt'
CI = Path('scripts/devtool/ci_artifacts_device.py')
RUNNER = Path('scripts/dev/android/m2_live_device.py')
GROUPED = Path('scripts/dev/android/r1_b1c_security_source.py')

class Violation(Exception): pass

def verify(root=ROOT):
    def read(p):
        f=root/p
        if not f.is_file() or f.is_symlink(): raise Violation('SOURCE_ABSENT_OR_SYMLINK:'+p.name)
        return f.read_text()
    ui,vm,app,main,ci,runner,grouped,browser_test=map(read,(UI_TEST,VM,APP,ACTIVITY,CI,RUNNER,GROUPED,BROWSER_TEST))
    required_ui=(
        'createAndroidComposeRule<MainActivity>()',
        'assumeTrue("SKYBIND_UI_NOT_REQUESTED", options.getString("skybind.ui.live") == "true")',
        'compose.onNodeWithTag("connect-readonly").performClick()',
        'compose.onNodeWithTag("disconnect-readonly").performClick()',
        'compose.onNodeWithTag("browser-up").performClick()',
        'compose.onNodeWithTag("browser-switch-remote").performClick()',
        'compose.onNodeWithTag("activity-filter-warnings").performScrollTo().performClick()',
        'compose.activityRule.scenario.recreate()',
        'SKYBIND_UI_FAILED_DISCONNECT_CLEANUP',
        'SKYBIND_UI_FAILED_RECONNECT',
        'SKYBIND_UI_BLOCKED_NO_FOLDER',
        'compose.onAllNodesWithText("$remote:$folder", substring = true)',
        'compose.onAllNodesWithText("$remote:/", substring = true)',
        'assertTrue("SKYBIND_UI_FAILED_JOBS_OPEN", tags("event-").isEmpty())',
        'assertTrue("SKYBIND_UI_FAILED_ACTIVITY_OPEN", tags("job-").isEmpty())',
        'compose.onNodeWithTag("jobs-view-activity").performScrollTo().performClick()',
        'compose.onNodeWithTag("activity-view-jobs").performScrollTo().performClick()',
        'step("SKYBIND_UI_FAILED_JOBS_OPEN")',
        'step("SKYBIND_UI_FAILED_ACTIVITY_OPEN")',
        'step("SKYBIND_UI_FAILED_ACTIVITY_FILTER")',
        'step("SKYBIND_UI_FAILED_ACTIVITY_RETURN")',
    )
    # Hosted compile regression 39360456956: onAllNodes is a rule member, not
    # a top-level extension; getOrNull is a semantics extension needing import.
    if 'import androidx.compose.ui.test.onAllNodes\n' in ui or \
       'import androidx.compose.ui.semantics.getOrNull\n' not in ui:
        raise Violation('M2_L2_COMPOSE_SEMANTICS_IMPORTS_INVALID')
    # Adding onDisconnect changed the SkybindApp positional call order; both
    # legacy BrowserState fixture parameters must now be explicitly named.
    if browser_test.count('browser = BrowserState(') != 2 or \
       'SkybindApp(snapshot(), {}, {}, BrowserState(' in browser_test:
        raise Violation('M2_L2_BROWSER_FIXTURE_NAMED_BROWSER_REQUIRED')
    for token in required_ui:
        if token not in ui: raise Violation('LIVE_UI_CONTRACT_MISSING:'+token[:75])
    for forbidden in ('su -c','Runtime.getRuntime().exec','Shell.cmd(', 'pm clear', 'am force-stop',
                      'stopService(', 'deleteFile(', 'SKYBIND_LIVE_NOT_REQUESTED'):
        if forbidden in ui: raise Violation('LIVE_UI_UNSAFE:'+forbidden)
    for token in ('fun disconnect()', 'active?.cancel()', 'generation++',
                  'clearBrowser()', 'bridge.close()',
                  'snapshot = SkybindReadSnapshot(LinkState.NOT_AUTHORIZED,'):
        if token not in vm: raise Violation('VM_DISCONNECT_MISSING:'+token)
    if 'session::disconnect' not in main or 'onDisconnect = session::disconnect' not in main:
        raise Violation('DISCONNECT_NOT_WIRED')
    if ('Modifier.testTag("disconnect-readonly")' not in app or
        'onClick = onDisconnect' not in app or 'RootService.stop' in vm):
        raise Violation('APP_DISCONNECT_UNSAFE_OR_MISSING')
    for token in ("'m2-ui-live': 'ui-live'", "'m2_l2_device_qualified'",
                  'M2-L2_REAL_COMPOSE_UI_BROWSE_DISCONNECT_RECONNECT',
                  'LANE_SCOPE_MISMATCH'):
        if token not in ci: raise Violation('CI_LANE_MISSING:'+token)
    for token in ('UI_CASE = ', "'skybind.ui.live'", 'parse_ui_live(',
                  'm2_l2_device_qualified=False', 'PASS_M2_L2_LIVE_UI_READONLY_RECOVERY',
                  'LIVE_UI_INSTRUMENTATION_INCOMPLETE_OR_UNCLASSIFIED'):
        if token not in runner: raise Violation('RUNNER_UI_LANE_MISSING:'+token)
    if ('scripts/dev/android/m2_ui_live_source_gate.py' not in grouped or
        'tests.test_m2_ui_live' not in grouped):
        raise Violation('GROUPED_SOURCE_GATE_NOT_INTEGRATED')
    return {'state':'PASS_M2_L2_LIVE_UI_SOURCE_ONLY',
            'android_built':False, 'device_qualified':False,
            'release_qualified':False, 'stale_ui_guard':True,
            'real_daemon_killed':False}

if __name__=='__main__':
    try: print(json.dumps(verify(), sort_keys=True))
    except (Violation, OSError, UnicodeError) as exc:
        print(json.dumps({'state':'FAILED_OR_BLOCKED','reason':str(exc)},sort_keys=True))
        raise SystemExit(2)
