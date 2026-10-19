#!/usr/bin/env python3
"""B1-C4..C7 grouped source campaign. No ADB, installations, or broker listener."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'build/evidence/android/b1c-consolidated/source'
CHECKS = [
    ['go', 'test', '-count=1', './internal/brokeridentity', './internal/brokeripc',
     './internal/brokergrant', './internal/brokerissue'],
    # Deterministic terminal-job cleanup regression; stress the former
    # TempDir-vs-worker persistence race, without running a build or ADB.
    ['go', 'test', '-count=30', './internal/daemon',
     '-run', '^TestB1RPCMountlessTransferBoundary$'],
    [sys.executable, '-B', '-m', 'unittest',
     'tests.test_r1_b1c_device', 'tests.test_r1_b1c3_identity',
     'tests.test_b1c_source_contract', 'tests.test_b1c_consolidated'],
    # Keep upstream-pin denial regressions in the regular grouped source lane.
    [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests/seal',
     '-p', 'test_*.py', '-v'],
    [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests/security',
     '-p', 'test_*.py', '-v'],
    [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests/webui',
     '-p', 'test_port.py', '-v'],
    [sys.executable, '-B', 'scripts/dev/android/m1_native_source_gate.py'],
    [sys.executable, '-B', 'scripts/dev/android/m2_browser_source_gate.py'],
    [sys.executable, '-B', 'scripts/dev/android/m2_live_source_gate.py'],
    [sys.executable, '-B', '-m', 'unittest', 'tests.test_m2_live_device', '-q'],
    [sys.executable, '-B', 'scripts/devtool/ci_artifacts_device_source_gate.py'],
    [sys.executable, '-B', '-m', 'unittest', 'scripts.devtool.test_ci_artifacts_device', '-q'],
    [sys.executable, '-B', '-m', 'unittest', 'tests.test_stable_signing', '-q'],
    [sys.executable, '-B', '-m', 'unittest', 'tests.test_m2_browser_source', '-q'],
    [sys.executable, '-B', '-m', 'unittest', 'tests.test_m1_native_app_source',
     'tests.test_m1_root_read_bridge_source'],
    [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests/contracts',
     '-p', 'test_*.py', '-v'],
]


def main() -> int:
    results = []
    for command in CHECKS:
        try:
            p = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=240)
            results.append({'command': command, 'exit_code': p.returncode,
                            'tail': (p.stdout + '\n' + p.stderr)[-1600:]})
        except (OSError, subprocess.TimeoutExpired) as exc:
            results.append({'command': command, 'exit_code': None,
                            'failure_class': type(exc).__name__})
    passed = all(item.get('exit_code') == 0 for item in results)
    report = {'schema': 'skybind-b1c-consolidated-source-v1',
              'state': 'PASS_B1C_CONSOLIDATED_SOURCE_ONLY' if passed else 'FAILED_OR_BLOCKED',
              'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
              'checks': results, 'android_instrumentation_executed': False,
              'hosted_build_executed': False, 'go_package_attestor_implemented': False,
              'cross_uid_broker_enabled': False, 'device_qualified': False,
              'release_qualified': False,
              'producer_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    if OUT.is_symlink():
        print(json.dumps({'state': 'FAILED_OR_BLOCKED', 'reason': 'RECEIPT_DIRECTORY_SYMLINK'}))
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / ('source-' + uuid.uuid4().hex + '.json')
    with path.open('x') as f:
        json.dump(report, f, indent=2, sort_keys=True)
        f.write('\n')
    print(json.dumps({'state': report['state'], 'receipt': str(path),
                      'checks': [{'exit_code': x.get('exit_code'), 'command': x['command']}
                                 for x in results]}, sort_keys=True))
    return 0 if passed else 2


if __name__ == '__main__':
    raise SystemExit(main())
