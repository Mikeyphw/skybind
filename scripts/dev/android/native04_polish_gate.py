#!/usr/bin/env python3
"""NATIVE-04 source promise guard; never claims APK build or on-device acceptance."""
from pathlib import Path
import json
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[3]
BASE=Path('android-app/app/src/main/java/io/github/mikeyphw/skybind')
ANDROID='{http://schemas.android.com/apk/res/android}'
class Violation(ValueError):pass

def need(value,reason):
    if not value:raise Violation(reason)

def verify(root=ROOT):
    def read(p):
        v=root/p
        need(v.is_file() and not v.is_symlink(),'MISSING_OR_LINKED:'+str(p))
        return v.read_text()
    model=read(BASE/'model/SkybindReadModel.kt')
    ui=read(BASE/'ui/SkybindApp.kt')
    presentation=read(BASE/'ui/NativePresentation.kt')
    reader=read(BASE/'bridge/LiveReadSnapshotReader.kt')
    broker=read(BASE/'bridge/RootReadBridgeService.kt')
    activity=read(BASE/'MainActivity.kt')
    agent=read(BASE/'bridge/R1PMBridgeAgent.kt')
    service=read(BASE/'bridge/R1AuthorityService.kt')
    tests=read(Path('android-app/app/src/androidTest/java/io/github/mikeyphw/skybind/NativePolishUiTest.kt'))
    gateway_test=read(Path('android-app/app/src/androidTest/java/io/github/mikeyphw/skybind/LiveReadGatewayTest.kt'))
    manifest=ET.fromstring(read(Path('android-app/app/src/main/AndroidManifest.xml')))
    permissions={p.attrib.get(ANDROID+'name') for p in manifest.findall('uses-permission')}
    need('android.permission.ACCESS_NETWORK_STATE' in permissions and
         not {'android.permission.INTERNET','android.permission.MANAGE_EXTERNAL_STORAGE',
              'android.permission.QUERY_ALL_PACKAGES'} & permissions,'UNSCOPED_ANDROID_PERMISSIONS')
    need('data class RuntimeIntegrity' in model and 'runtime = null' in model and
         'sampledAtMillis = null' in model and 'fun failClosed()' in model,'STALE_RUNTIME_NOT_HIDDEN')
    need('read("runtime.status")' in reader and 'runtime.opt("ready") !is Boolean' in reader and
         'runtime.opt("provenance_valid") !is Boolean' in reader and
         'runtime = runtimeIntegrity' in reader and 'sampledAtMillis = System.currentTimeMillis()' in reader,
         'RUNTIME_HEALTH_NOT_AUTHORITATIVE')
    need('"mount.health"' in broker and 'if (op == "mount.health")' in broker and
         'if (!jobName.matches(name))' in broker and
         'rpc(method, "query", checkedReadArguments(method, arguments))' in broker,
         'MOUNT_HEALTH_QUERY_AUTHORITY_ESCALATED')
    need('read("mount.health", JSONObject().put("name", name))' in reader and
         'health.optString("name") != name' in reader and 'health.optInt("attempts", -1) !in 0..100' in reader and
         'recoveryAttempts: Int?' in model,'MOUNT_HEALTH_IDENTITY_NOT_BOUND')
    need('Runtime integrity' in ui and 'FUSE availability not implied' in ui and
         'home-network' in ui and 'diagnostics-network' in ui and
         'overall FUSE device health not reported' in ui,'DASHBOARD_FALSE_HEALTH_CLAIM')
    need('val peerConnected: Boolean' in agent and 'bkxPeerConnected' in activity and
         'bkxStarting' in ui and 'bkxStartFailed' in ui and
         'if (bkxAuthorityRunning && bkxPeerConnected)' not in ui and
         'bkxAuthorityRunning && bkxPeerConnected' in ui and
         'onEnableBkx = ::enableAuthority' in activity and
         'bkx-background-lifetime' in ui and 'if (!bkxKeepBackground && R1AuthorityService.isRunning) disableAuthority()' in activity and
         'putBoolean("bkx_keep_background", keep)' in activity and
         'enableAuthority()' not in activity.split('override fun onStart()',1)[1].split('override fun onStop()',1)[0] and
         'R1PMBridgeAgent.start(applicationContext)' in activity and
         'startForeground(NOTIFICATION, note)' in service,
         'BKX_STATUS_OR_OPTIN_NOT_GROUNDED')
    need('items(s.activeJobs.take(64)' in ui and 'items(s.recentJobs.take(64)' in ui and
         'items(filtered, key = { it.sequence })' in ui and
         'activity-journal-gap' in ui and 'activity-filter-errors' in ui and
         'job-receipt-${job.id}' in ui and
         'NativePresentation.time(event.occurredAt)' in ui,'JOBS_ACTIVITY_LAZY_OR_HUMAN_VIEW_MISSING')
    need('rememberLazyListState()' in ui and 'LaunchedEffect(browse.remote, browse.path)' in ui and
         'itemsIndexed(browse.entries.take(200)' in ui and
         'browse.remote}:${browse.path}:${entry.directory}:${entry.name}' in ui and
         'sizeIn(minWidth = 48.dp, minHeight = 48.dp)' in ui and
         'contentDescription = "${entry.label} tab"' in ui,'BROWSER_OR_ACCESSIBILITY_REGRESSED')
    need('BuildConfig.VERSION_NAME' in presentation and 'GET_SIGNING_CERTIFICATES' in presentation and
         'MessageDigest.getInstance("SHA-256")' in presentation and
         'about-show-signer' in ui and 'about-app-version' in ui and
         'Module version' in ui and 'not reported' in ui.lower() and
         'privacy' in ui.lower(),'BUILD_PROVENANCE_PRIVACY_MISSING')
    for case in ('homeShowsEvidenceNotHealthyGuess','diagnosticsAndBkxStatesAreVisibleWithoutBackgroundActivation',
                 'activityFiltersAndReceiptDetailsRemainReadOnly','scaledFontsAndLandscapeLayoutRetainNavigationSemantics'):
        need('fun '+case in tests,'ANDROID_POLISH_FIXTURE_TEST_MISSING:'+case)
    for case in ('rejectsMissingRuntimeEvidenceInsteadOfInferringHealthy','supervisorHealthCannotIdentifyAnotherMount',
                 'healthRecoveryEvidenceIsBounded'):
        need('fun '+case in gateway_test,'ANDROID_NEGATIVE_EVIDENCE_TEST_MISSING:'+case)
    return {'state':'PASS_NATIVE_04_POLISH_SOURCE_ONLY','android_built':False,
            'device_qualified':False,'personal_apk_qualified':False,'backend_mutations_added':False}

if __name__=='__main__':
    try:print(json.dumps(verify(),sort_keys=True))
    except (Violation,OSError,ET.ParseError) as exc:
        print(json.dumps({'state':'BLOCKED_NATIVE_04','reason':str(exc)},sort_keys=True))
        raise SystemExit(2)
