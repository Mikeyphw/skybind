#!/usr/bin/env python3
"""Consolidated M2-L3 source-only guard; no ADB/device/APK operations here."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[3]
TRANSPORT = Path('android-app/app/src/androidTest/java/io/github/mikeyphw/skybind/LiveTransportAcceptanceTest.kt')
SESSION = Path('android-app/app/src/main/java/io/github/mikeyphw/skybind/bridge/RootReadSession.kt')
PROCESS = Path('scripts/dev/android/m2_process_live.py')
LIVE = Path('scripts/dev/android/m2_live_device.py')
CI = Path('scripts/devtool/ci_artifacts_device.py')
CONFIG = Path('.devtool.toml')


class Violation(Exception):
    pass


def verify(root=ROOT):
    def read(rel):
        path = root / rel
        if not path.is_file() or path.is_symlink():
            raise Violation('MISSING_' + path.name)
        return path.read_text()

    transport, session, process, runner, ci, config = map(
        read, (TRANSPORT, SESSION, PROCESS, LIVE, CI, CONFIG))

    def check(doc, label, tokens):
        for t in tokens:
            if t not in doc:
                raise Violation(label + ':' + t)

    check(transport, 'TRANSPORT_TEST_REQUIRED', (
        'class LiveTransportAcceptanceTest', 'skybind.transport.live',
        'RootReadSession(app)', 'withContext(Dispatchers.Main) { session.transportLost() }',
        'SKYBIND_TRANSPORT_FAILED_DUPLICATE_CALLBACK',
        'SKYBIND_TRANSPORT_FAILED_STALE_DATA',
        'SKYBIND_TRANSPORT_FAILED_RECONNECT',
        'withContext(NonCancellable + Dispatchers.Main) { session.close() }'))
    check(session, 'SESSION_FAIL_CLOSED_REQUIRED', (
        'if (connection !== this) return', 'transportLost()',
        'if (connection !== boundConnection)',
        'withContext(Dispatchers.Main) { transportLost() }',
        'catch (cancel: CancellationException)',
        'reader = LiveReadSnapshotReader()',
        'if (remote !== api || reader !== ownedReader)',
        'if (remote !== api) throw SecurityException',
        'old?.let { runCatching { RootService.unbind(it) } }'))
    for forbidden in ('RootService.stop(', 'Runtime.getRuntime()', 'killProcess(',
                      'Shell.cmd(', 'su -c', 'am force-stop'):
        if forbidden in transport or forbidden in session:
            raise Violation('TRANSPORT_UNSAFE:' + forbidden)
    check(process, 'PROCESS_OPT_IN_REQUIRED', (
        "raise live.Blocked('EXPLICIT_APP_FORCE_STOP_REQUIRED')",
        "component = live.APP + '/.MainActivity'",
        "shell('am', 'force-stop', live.APP",
        "shell('pidof', live.APP", "'Not authorized' in texts",
        "el.attrib.get('package') == live.APP",
        "any('Connect' in text and 'root approval required' in text for text in texts)",
        "shell('rm', '-f', dump", "m2_l3_process_device_qualified=False",
        "'M2-L3_APP_FORCE_STOP_COLD_LAUNCH_UI_ONLY'"))
    for forbidden in ('"su"', "'su'", "'reboot'", "'pm', 'clear'", "'uninstall'",
                      'RootService.stop(', 'shell=True', 'os.system('):
        if forbidden in process or forbidden in ci:
            raise Violation('PROCESS_MUTATION:' + forbidden)
    check(runner, 'TRANSPORT_SIGNED_RUNNER_REQUIRED', (
        "TRANSPORT_CASE = APP + '.LiveTransportAcceptanceTest#liveTransportLossAndFreshReconnect'",
        "'-e', 'skybind.transport.live', 'true'",
        'parse_transport_live(', 'm2_l3_transport_device_qualified=False',
        "doc['m2_l3_transport_device_qualified'] = True",
        "M2-L3_APP_OWNED_TRANSPORT_LOSS_RECOVERY_ONLY"))
    check(ci, 'CANONICAL_LANES_REQUIRED', (
        "'m2-transport-live': 'transport-live'", "'m2-process-live': 'process-live'",
        "--allow-app-force-stop", 'APP_FORCE_STOP_FLAG_REQUIRES_PROCESS_LANE',
        'M2_PROCESS_EXPLICIT_FORCE_STOP_AUTHORIZATION_REQUIRED',
        "process.run(opts) if lane == 'm2-process-live' else live.run(opts)",
        'live.verify_candidate(folder, args.run_id, sha, pin)',
        'live.installed_pair(serial, manifest, pin)',
        "record.get('m2_l3_process_device_qualified', False)",
        "record.get('m2_l3_transport_device_qualified', False)",
        'M2-L3_APP_FORCE_STOP_COLD_LAUNCH_UI_ONLY'))
    check(config, 'DEVTOOL_LIFECYCLE_DAG_REQUIRED', (
        '[targets.skybind_release.workflows]', 'm2-lifecycle-source = [',
        '[targets.skybind_release.jobs.m2-lifecycle-source]',
        '[targets.skybind_release.jobs.m2-lifecycle-unit]',
        '[targets.skybind_release.jobs.m2-lifecycle-security]',
        '[wrapper.commands.m2-lifecycle-source]'))
    return {'state': 'PASS_M2_L3_CONSOLIDATED_LIFECYCLE_SOURCE_ONLY',
            'device_qualified': False, 'app_force_stopped': False,
            'actual_daemon_death_tested': False, 'actual_root_revocation_tested': False,
            'hosted_apk_built': False, 'release_qualified': False}


if __name__ == '__main__':
    try:
        print(json.dumps(verify(), sort_keys=True))
    except (Violation, OSError, UnicodeError) as exc:
        print(json.dumps({'state': 'FAILED_OR_BLOCKED', 'reason': str(exc)}, sort_keys=True))
        raise SystemExit(2)
