#!/usr/bin/env python3
"""Opt-in app-only force-stop/cold-launch M2-L3 gate, never privileged daemon death.

Only called from authenticated exact APK pair launcher. The external device-side
observer uses UIAutomator's XML snapshot, not an injected root grant or APK test
that would itself be destroyed by the force-stop. Drops its own temporary XML.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import re
import sys
import uuid
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import m2_live_device as live


def verify_app_cold_launch(serial: str, *, approved: bool, mark_force_stop=None, mark_done=None):
    if not approved:
        raise live.Blocked('EXPLICIT_APP_FORCE_STOP_REQUIRED')
    component = live.APP + '/.MainActivity'
    def shell(*args, timeout=45, ok=True):
        return live.adb(serial, 'shell', *args, timeout=timeout, ok=ok)
    def start():
        done = shell('am', 'start', '-W', '-n', component, timeout=45, ok=False)
        if done.returncode != 0 or 'Error:' in done.stdout or 'Error:' in done.stderr:
            raise live.Blocked('M2_PROCESS_ACTIVITY_LAUNCH_FAILED')
    # Set an observed app process to stop; avoid claiming force-stop of a process
    # which was not running. App startup must be no-root and read-only.
    start()
    before = shell('pidof', live.APP, ok=False)
    if before.returncode != 0 or not before.stdout.strip():
        raise live.Blocked('M2_PROCESS_PRESTOP_PID_NOT_OBSERVED')
    if not re.fullmatch(r'[0-9\s]+', before.stdout):
        raise live.Blocked('M2_PROCESS_PID_UNRECOGNIZED')
    if mark_force_stop is not None: mark_force_stop()
    stopped = shell('am', 'force-stop', live.APP, timeout=30, ok=False)
    if stopped.returncode != 0:
        raise live.Blocked('M2_PROCESS_APP_FORCE_STOP_FAILED')
    if mark_done is not None: mark_done()
    after = shell('pidof', live.APP, ok=False)
    if after.stdout.strip():
        raise live.Blocked('M2_PROCESS_APP_STILL_RUNNING_AFTER_STOP')
    start()
    cold = shell('pidof', live.APP, ok=False)
    if cold.returncode != 0 or not cold.stdout.strip() or not re.fullmatch(r'[0-9\s]+', cold.stdout):
        raise live.Blocked('M2_PROCESS_COLD_PID_NOT_OBSERVED')
    if set(before.stdout.split()) & set(cold.stdout.split()):
        raise live.Blocked('M2_PROCESS_PID_REUSED_OR_NOT_RESTARTED')
    # Use one unique owned device path, never a user-selected path. The dump is
    # deliberately NOT copied into the evidence receipt (privacy, app state).
    dump = '/sdcard/Download/skybind-m2-cold-' + uuid.uuid4().hex + '.xml'
    try:
        for _ in range(3):
            result = shell('uiautomator', 'dump', dump, timeout=60, ok=False)
            if result.returncode != 0:
                continue
            raw = shell('cat', dump, timeout=30, ok=False)
            if raw.returncode != 0 or not 0 < len(raw.stdout) < 512_000:
                continue
            try:
                document = ET.fromstring(raw.stdout)
            except ET.ParseError:
                continue
            texts = [el.attrib.get('text', '') for el in document.iter('node')
                     if el.attrib.get('package') == live.APP]
            if ('Not authorized' in texts and
                    any('Connect' in text and 'root approval required' in text for text in texts)):
                if any(text == 'Connected' for text in texts):
                    raise live.Blocked('M2_PROCESS_AUTO_CONNECTED_STATE')
                return {'previous_pid_sha256': hashlib.sha256(before.stdout.strip().encode()).hexdigest(),
                        'cold_pid_sha256': hashlib.sha256(cold.stdout.strip().encode()).hexdigest(),
                        'cold_ui_observed': True, 'new_process_observed': True}
        raise live.Blocked('M2_PROCESS_COLD_UI_NOT_OBSERVABLE')
    finally:
        shell('rm', '-f', dump, timeout=30, ok=False)


def run(opts):
    doc = dict(schema='skybind-m2-live-v1', state='BLOCKED', reason=None,
               source_sha=opts.source_sha, github_run_id=opts.run_id,
               artifact_id=opts.artifact_id, installed_pair_verified=True,
               signing_verified=True, device_qualified=False,
               m2_l1_device_qualified=False, m2_l2_device_qualified=False,
               m2_l3_negative_device_qualified=False, m2_l3_transport_device_qualified=False,
               m2_l3_process_device_qualified=False, release_qualified=False,
               daemon_mutated=False, root_grant_changed_by_runner=False,
               app_force_stop_attempted=False, app_force_stop_performed=False, qualified_scope=None,
               recorded_at_utc=datetime.now(timezone.utc).isoformat())
    try:
        if not opts.allow_app_force_stop:
            raise live.Blocked('EXPLICIT_APP_FORCE_STOP_REQUIRED')
        details = verify_app_cold_launch(opts.serial, approved=True,
                  mark_force_stop=lambda: doc.update(app_force_stop_attempted=True),
                  mark_done=lambda: doc.update(app_force_stop_performed=True))
        doc.update(details)
        doc['state'] = 'PASS_M2_L3_APP_PROCESS_COLD_LAUNCH'
        doc['qualified_scope'] = 'M2-L3_APP_FORCE_STOP_COLD_LAUNCH_UI_ONLY'
        doc['m2_l3_process_device_qualified'] = True
    except (live.Blocked, ValueError, OSError) as exc:
        doc['reason'] = exc.reason if isinstance(exc, live.Blocked) else type(exc).__name__.upper()
        # A force-stop may already have occurred when a later step blocks;
        # never claim no device mutation merely because acceptance did not pass.
        # The marker above remains true even when UIAutomator blocks or fails.
    doc['receipt'] = live.store(doc)
    print(json.dumps({k: doc.get(k) for k in ('state','reason','source_sha','github_run_id',
              'artifact_id','installed_pair_verified','m2_l1_device_qualified', 'm2_l2_device_qualified',
              'm2_l3_negative_device_qualified', 'm2_l3_transport_device_qualified',
              'm2_l3_process_device_qualified', 'app_force_stop_performed','receipt')}, sort_keys=True))
    return 0 if doc['state'].startswith('PASS_') else 2
