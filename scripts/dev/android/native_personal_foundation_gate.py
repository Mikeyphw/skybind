#!/usr/bin/env python3
"""NATIVE-00/01 static source guard; not Android compilation/device qualification."""
from pathlib import Path
import json
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
MAIN = Path('android-app/app/src/main/java/io/github/mikeyphw/skybind')
ANDROID = '{http://schemas.android.com/apk/res/android}'

class Violation(Exception): pass

def need(ok, code):
    if not ok: raise Violation(code)

def verify(root=ROOT):
    def read(path):
        p = root / path
        need(p.is_file() and not p.is_symlink(), 'FILE_MISSING_OR_SYMLINK:'+str(path))
        return p.read_text()
    activity = read(MAIN/'MainActivity.kt')
    ui = read(MAIN/'ui/SkybindApp.kt')
    viewmodel = read(MAIN/'bridge/SkybindSessionViewModel.kt')
    session = read(MAIN/'bridge/RootReadSession.kt')
    broker = read(MAIN/'bridge/RootReadBridgeService.kt')
    reader = read(MAIN/'bridge/LiveReadSnapshotReader.kt')
    manifest = ET.fromstring(read(Path('android-app/app/src/main/AndroidManifest.xml')))
    app = manifest.find('application')
    need(app is not None and app.attrib.get(ANDROID+'label')=='Skybind' and
         app.attrib.get(ANDROID+'icon')=='@mipmap/ic_launcher', 'BRANDING_MANIFEST_MISSING')
    adaptive = ET.fromstring(read(Path('android-app/app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml')))
    need(adaptive.tag=='adaptive-icon' and set(x.tag for x in adaptive)==
         {'background','foreground','monochrome'}, 'ADAPTIVE_ICON_INCOMPLETE')
    for name in ('ic_launcher_foreground','ic_launcher_monochrome','ic_launcher_background'):
        vector = ET.fromstring(read(Path('android-app/app/src/main/res/drawable')/(name+'.xml')))
        need(vector.tag=='vector', 'ANDROID_VECTOR_INVALID:'+name)
    need('session.onForeground()' in activity and 'session.onBackground()' in activity and
         'onConnect = session::connect' in activity and 'RootService.bind' in session and
         'fun onForeground()' in viewmodel and 'if (autoConnectEnabled && !explicitlyDisconnected && !initialAttempted)' in viewmodel and
         'private fun connectInternal()' in viewmodel and 'reconnectUsed = true' in viewmodel and
         'getSharedPreferences("skybind_native", 0)' in viewmodel, 'AUTO_ROOT_POLICY_MISSING')
    need('BKX background authority' in ui and 'bkxAuthorityRunning' in ui and
         'R1AuthorityService.isRunning' in activity and 'authorityRunning = true' not in activity,
         'BKX_SERVICE_STATE_NOT_OBSERVED')
    need('MOUNTS("Mounts"' in ui and 'MountsPage(safe' in ui and
         'items(s.mounts, key = { it.id })' in ui and
         'itemsIndexed(browse.entries.take(200)' in ui and
         '"screen-mounts"' in ui and '"nav-" + entry.label.lowercase()' in ui,
         'MOUNT_NAVIGATION_OR_LAZY_BROWSER_MISSING')
    need('"mount.status"' in broker and '"mount.status"' in reader and
         'if (op == "mount.status")' in broker and 'input.length() != 1' in broker and
         'rpc(method, "query", checkedReadArguments(method, arguments))' in broker and
         'value.optString("name") != name' in reader and
         'observed !in setOf("RUNNING", "STOPPED", "DEGRADED", "MOUNT_STALE")' in reader and
         'throw SnapshotStageException("mount.status")' in reader,
         'MOUNT_AUTHORITY_NOT_FAIL_CLOSED')
    for forbidden in ('"mount.start"', '"mount.stop"', '"config.apply"', '"mount.restart"', '"mount.reconcile"'):
        need(forbidden not in broker, 'MOUNT_WRITE_UNREVIEWED:'+forbidden)
    return {'state':'PASS_NATIVE_FOUNDATION_SOURCE_ONLY', 'android_built':False,
            'device_qualified':False, 'release_qualified':False,
            'historical_apk_evidence_compatible':False}

if __name__=='__main__':
    try: print(json.dumps(verify(),sort_keys=True))
    except (Violation,OSError,ET.ParseError) as e:
        print(json.dumps({'state':'FAILED_OR_BLOCKED','reason':str(e)},sort_keys=True))
        raise SystemExit(2)
