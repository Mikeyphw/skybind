#!/usr/bin/env python3
"""Fail-closed source checks for opt-in persistent Android PM authority.
No device state, grants or backups change while executing this gate.
"""
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
ANDROID = ROOT / 'android-app/app/src/main'
AGENT = ANDROID / 'java/io/github/mikeyphw/skybind/bridge/R1PMBridgeAgent.kt'
SERVICE = ANDROID / 'java/io/github/mikeyphw/skybind/bridge/R1AuthorityService.kt'
ACTIVITY = ANDROID / 'java/io/github/mikeyphw/skybind/MainActivity.kt'
MANIFEST = ANDROID / 'AndroidManifest.xml'

def check():
    agent, service, activity = (p.read_text() for p in (AGENT, SERVICE, ACTIVITY))
    app = ET.parse(MANIFEST).getroot()
    ns = '{http://schemas.android.com/apk/res/android}'
    service_manifest = app.find("./application/service[@" + ns + "name='.bridge.R1AuthorityService']")
    permissions = {p.get(ns+'name') for p in app.findall('uses-permission')}
    checks = {
        'EXPLICIT_VISIBLE_AUTHORITY': 'Enable BKX bridge' in activity and 'Stop bridge' in activity,
        'FOREGROUND_SERVICE_IS_NOT_EXPORTED': service_manifest is not None and service_manifest.get(ns+'exported') == 'false',
        'FOREGROUND_SPECIAL_USE_DECLARED': service_manifest is not None and service_manifest.get(ns+'foregroundServiceType') == 'specialUse'
            and 'android.permission.FOREGROUND_SERVICE_SPECIAL_USE' in permissions,
        'NO_AUTOMATIC_BOOT': 'BOOT_COMPLETED' not in service and 'START_STICKY' not in service.replace('START_NOT_STICKY',''),
        'SERVICE_LIFETIME_SURVIVES_APP_SWITCH': 'if (!R1AuthorityService.isRunning) R1PMBridgeAgent.stop()' in activity,
        'EXPLICIT_STOP_DISCONNECTS': 'R1PMBridgeAgent.stop()' in service and 'stopSelf()' in service,
        'SOCKET_READ_DOES_NOT_TIMEOUT_IDLE_SESSION': 'socket.soTimeout = 0' in agent,
        'NO_SHELL_NO_GRANTS_IN_ANDROID': not any(x in service + activity for x in ('su -c', 'ProcessBuilder(', 'grantToken', 'issueGrant(')),
        'NO_PACKAGE_VISIBILITY_ESCALATION': len(app.findall('./queries/package')) == 1 and
            app.find('./queries/package').get(ns+'name') == 'com.mikeyphw.bkx.android',
    }
    for name, ok in checks.items():
        print(('PASS_' if ok else 'FAIL_') + name)
    return 0 if all(checks.values()) else 2

if __name__ == '__main__':
    raise SystemExit(check())
