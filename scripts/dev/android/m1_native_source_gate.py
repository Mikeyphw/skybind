#!/usr/bin/env python3
"""Native foreground auto-root M1 source contract; never builds APKs locally."""
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

    need('SkybindSessionViewModel by viewModels()' in activity and
         'onConnect = session::connect' in activity and 'onRefresh = session::refresh' in activity and
         'session.onForeground()' in activity and 'session.onBackground()' in activity,
         'PRODUCTION_CONNECT_FLOW_MISSING')
    bridge = read(MAIN / 'bridge/RootReadBridgeService.kt')
    session = read(MAIN / 'bridge/RootReadSession.kt')
    viewmodel = read(MAIN / 'bridge/SkybindSessionViewModel.kt')
    reader = read(MAIN / 'bridge/LiveReadSnapshotReader.kt')
    aidl = read(Path('android-app/app/src/main/aidl/io/github/mikeyphw/skybind/bridge/IRootReadBridge.aidl'))
    settings = read(Path('android-app/settings.gradle.kts'))
    gateway_test = read(TEST / 'LiveReadGatewayTest.kt')
    need('RootReadSession(app)' in viewmodel and 'root service' in session.lower() and
         'suspend fun connect()' in session and 'RootService.bind' in session and
         'fun onForeground()' in viewmodel and 'autoConnectEnabled' in viewmodel and
         'private fun connectInternal()' in viewmodel and
         'if (foreground && autoConnectEnabled && !explicitlyDisconnected && !reconnectUsed)' in viewmodel and
         'reconnectUsed = true' in viewmodel and 'fun onBackground()' in viewmodel,
         'AUTO_ROOT_CONNECT_FLOW_MISSING')
    need('Binder.getCallingUid()' in bridge and 'getPackagesForUid(caller)' in bridge and
         'GET_SIGNING_CERTIFICATES' in bridge and 'Process.myUid() != 0' in bridge,
         'BINDER_CALLER_VERIFICATION_MISSING')
    need('Os.lstat' in bridge and 'socket.peerCredentials.uid != 0' in bridge and
         'socket.shutdownOutput()' in bridge and '262144' in bridge and '65536' in bridge,
         'ROOT_SOCKET_BOUNDARY_UNVERIFIED')
    read_methods = ('system.capabilities', 'runtime.status', 'provider.remotes', 'mount.list', 'mount.status', 'jobs.status', 'operation.events')
    need(all('"' + method + '"' in bridge and '"' + method + '"' in reader for method in read_methods),
         'READ_ONLY_METHOD_NOT_EXPLICIT')
    need('rpc(method, "query", checkedReadArguments(method, arguments))' in bridge and
         'RootService.bind' in session and
         'root service' in session.lower() and 'Shell.cmd(' not in bridge + session,
         'UNSAFE_ROOT_EXECUTION_PATH')
    # NATIVE-02 replaces the M1 read-only mount prohibition with exact typed
    # preview/confirm, authenticated root ownership and bounded daemon operations.
    for forbidden in ('"config.apply"', '"provider.crypt.password.set"',
                      '"remote.transfer.start"', '"remote.transfer.cancel"'):
        need(forbidden not in bridge, 'UNREVIEWED_BROKER_METHOD_' + forbidden)
    need(all(('"mount.'+action+'"') in bridge for action in
             ('start','stop','restart','reconcile')) and
         'private fun previewMountTicket(' in bridge and
         'override fun confirmMount(' in bridge and
         'mountTickets.remove(previewId)' in bridge and
         'mountTicket.session != session' in bridge and
         'registry.optLong("revision", -1) != mountTicket.revision' in bridge and
         'checkedMountState(mountTicket.name)' in bridge and
         'socket.peerCredentials.uid != 0' in bridge and
         'fun previewMount(' in session and 'fun confirmMount(' in session and
         all('String preview'+action+'Mount(' in aidl for action in ('Start','Stop','Restart','Reconcile')) and
         'String confirmMount(' in aidl,
         'MOUNT_LIFECYCLE_TYPED_AUTHORITY_MISSING')
    # M3-specific run/cancel are distinct from M1's unchanged query endpoint.
    need('tickets.remove(previewId)' in bridge and
         'mountTicket.session != session' in bridge and
         'ownedRuns[runId] != session' in bridge and
         'rpc("job.run", "run", JSONObject()' in bridge and
         'rpc("operation.cancel", "cancel", JSONObject().put("id", runId))' in bridge,
         'M3_OPERATIONS_BYPASS_M1_QUERY_GATE')
    need('withTimeout(20_000L)' in session and 'val api = remote ?:' in session and
         'fun reset()' in reader and reader.count('optBoolean("cursor_reset")') == 2 and 'gap' in reader,
         'FAIL_CLOSED_REPLAY_OR_CONNECT_MISSING')
    need('interface IRootReadBridge' in aidl and 'String query(' in aidl and
         'aidl = true' in gradle and 'com.github.topjohnwu.libsu:service:6.0.0' in gradle and
         'https://jitpack.io' in settings,
         'ANDROID_BINDER_DEPENDENCIES_MISSING')
    need('fun mapsRealDaemonShapeIntoJobsAndChronologicalActivity' in gateway_test and
         'fun rejectsFailedRpcResponse' in gateway_test and
         'fun gapResetsPreviouslyObservedEvents' in gateway_test,
         'LIVE_GATEWAY_DEVICE_TESTS_MISSING')
    need('suspend fun snapshot()' in model and 'fun failClosed()' in model and
         'jobs = emptyList()' in model and 'events = emptyList()' in model and
         'remotes = emptyList()' in model and 'hasEventGap = false' in model,
         'STALE_BACKEND_DATA_NOT_CLEARED')
    need('val activeJobs' in model and 'val timeline' in model and 'events.distinctBy' in model,
         'JOB_JOURNAL_BOUNDARIES_NOT_EXPLICIT')
    for key in ('screen-home', 'screen-mounts', 'screen-browser', 'screen-jobs', 'screen-more'):
        # Dynamic screen tag construction must match exact tab display names.
        need(key.split('-')[1].capitalize() in ui and '"screen-" + title.lowercase()' in ui,
             'SCREEN_TAG_MISSING_' + key)
    for key in ('"nav-" + entry.label.lowercase()', '"action-refresh"', '"browser-search"',
                '"activity-filter-warnings"', '"cancel-${job.id}"', '"browser-write-disabled"'):
        need(key in ui, 'UI_SEMANTIC_TAG_MISSING_' + key)
    need('enabled = false' in ui and 'val safe = snapshot.failClosed()' in ui and
         'connect-readonly' in ui and 'onConnect: () -> Unit' in ui and
         'onAutoConnectChanged' in ui and 'MountsPage(safe' in ui and
         'items(s.mounts, key = { it.id })' in ui and
         'itemsIndexed(browse.entries.take(200)' in ui,
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
    return {'state': 'PASS_M1_FOREGROUND_AUTO_BRIDGE_SOURCE_ONLY', 'screens': 5,
            'instrumentation_source_tests': 11, 'read_only_gateway': 'ROOT_SERVICE_FOREGROUND_AUTO_APPROVAL',
            'broker_authenticated': False, 'device_tests_executed': False,
            'github_apks_built': False, 'release_qualified': False}

if __name__ == '__main__':
    try:
        print(json.dumps(verify(), sort_keys=True))
    except (Violation, OSError, UnicodeError) as exc:
        print(json.dumps({'state': 'FAILED_OR_BLOCKED', 'reason': str(exc)}, sort_keys=True))
        raise SystemExit(2)
