#!/usr/bin/env python3
"""Read-only M1 native Android source contract; never builds APKs locally."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MAIN = Path('android-app/app/src/main/java/io/github/mikeyphw/skybind')
TEST = Path('android-app/app/src/androidTest/java/io/github/mikeyphw/skybind')

class Violation(Exception):
    pass

def need(condition, reason):
    if not condition:
        raise Violation(reason)

def verify(root: Path = ROOT) -> dict:
    def read(path: Path) -> str:
        actual = root / path
        need(actual.is_file() and not actual.is_symlink(), 'SOURCE_MISSING_OR_SYMLINK_' + path.name)
        return actual.read_text('utf-8')

    activity = read(MAIN / 'MainActivity.kt')
    model = read(MAIN / 'model/SkybindReadModel.kt')
    ui = read(MAIN / 'ui/SkybindApp.kt')
    test = read(TEST / 'NativeUiTest.kt')
    lifecycle = read(TEST / 'NativeLifecycleTest.kt')
    manifest = read(Path('android-app/app/src/main/AndroidManifest.xml'))
    gradle = read(Path('android-app/app/build.gradle.kts'))
    workflow = read(Path('.github/workflows/skybind-android-apks.yml'))

    need('ReadOnlyCoordinator(UnpairedGateway())' in activity and 'SkybindApp(snapshot = snapshot' in activity,
         'PRODUCTION_NOT_DEFAULT_DENY')
    need('suspend fun snapshot()' in model and 'fun failClosed()' in model and
         'jobs = emptyList()' in model and 'events = emptyList()' in model and
         'remotes = emptyList()' in model and 'hasEventGap = false' in model,
         'STALE_BACKEND_DATA_NOT_CLEARED')
    need('val activeJobs' in model and 'val timeline' in model and 'events.distinctBy' in model,
         'JOB_JOURNAL_BOUNDARIES_NOT_EXPLICIT')
    for key in ('screen-home', 'screen-browser', 'screen-jobs', 'screen-activity', 'screen-more'):
        # Dynamic screen tag construction must match exact tab display names.
        need(key.split('-')[1].capitalize() in ui and '"screen-" + title.lowercase()' in ui,
             'SCREEN_TAG_MISSING_' + key)
    for key in ('"nav-" + entry.label.lowercase()', '"action-refresh"', '"browser-search"',
                '"activity-filter-warnings"', '"cancel-${job.id}"', '"browser-write-disabled"'):
        need(key in ui, 'UI_SEMANTIC_TAG_MISSING_' + key)
    need('enabled = false' in ui and 'val safe = snapshot.failClosed()' in ui,
         'UNAUTHORIZED_OPERATION_NOT_DISABLED')
    need('fun realNavigationHasFiveDistinctPages' in test and
         'fun activityIsAJournalNotAnActionableJobQueue' in test and
         'fun unpairedStateHidesStaleServerData' in test,
         'NATIVE_DEVICE_TEST_MATRIX_MISSING')
    need('fun selectedTabSurvivesActivityRecreation' in lifecycle and 'scenario.recreate()' in lifecycle,
         'ACTIVITY_RECREATION_TEST_MISSING')
    for forbidden in ('android.permission.INTERNET', 'android.permission.MANAGE_EXTERNAL_STORAGE',
                      'android.permission.QUERY_ALL_PACKAGES', 'android.permission.REQUEST_INSTALL_PACKAGES'):
        need(forbidden not in manifest, 'UNEXPECTED_ANDROID_PERMISSION_' + forbidden)
    need('android:exported="true"' in manifest and manifest.count('android:exported="true"') == 1,
         'APP_COMPONENT_EXPORT_CONTRACT_DRIFT')
    for forbidden in ('Runtime.getRuntime(', 'ProcessBuilder(', 'su -c', 'su\"', '127.0.0.1:',
                      'LocalSocketAddress(', 'SkybindReadSnapshot(LinkState.ONLINE'):
        need(forbidden not in (activity + model + ui), 'UNREVIEWED_PRIVILEGED_APP_TRANSPORT_' + forbidden)
    need('ui-test-manifest' in gradle and 'ui-test-junit4' in gradle and
         ':app:assembleDebug :app:assembleDebugAndroidTest' in workflow,
         'ANDROID_TEST_BUILD_CONTRACT_DRIFT')
    return {'state': 'PASS_M1_NATIVE_SOURCE_ONLY', 'screens': 5,
            'instrumentation_source_tests': 5, 'read_only_gateway': 'UNPAIRED_DEFAULT_DENY',
            'broker_authenticated': False, 'device_tests_executed': False,
            'github_apks_built': False, 'release_qualified': False}

if __name__ == '__main__':
    try:
        print(json.dumps(verify(), sort_keys=True))
    except (Violation, OSError, UnicodeError) as exc:
        print(json.dumps({'state': 'FAILED_OR_BLOCKED', 'reason': str(exc)}, sort_keys=True))
        raise SystemExit(2)
