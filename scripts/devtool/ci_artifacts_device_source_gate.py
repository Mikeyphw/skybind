#!/usr/bin/env python3
"""Skybind CI/device integration source contract, no adb/GitHub side effects."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]
CLI = Path('scripts/devtool/ci_artifacts_device.py')
LANE = Path('scripts/dev/android/m2_live_device.py')
TESTS = Path('scripts/devtool/test_ci_artifacts_device.py')
GROUPED = Path('scripts/dev/android/r1_b1c_security_source.py')

class Violation(Exception):
    pass


def need(value, code):
    if not value:
        raise Violation(code)


def verify(root=ROOT):
    def read(rel):
        p = root / rel
        need(p.is_file() and not p.is_symlink(), 'FILE_MISSING_' + p.name)
        return p.read_text()
    cli, lane, tests, grouped = map(read, (CLI, LANE, TESTS, GROUPED))
    required = (
        "REPO = 'Mikeyphw/skybind'",
        "ARTIFACT = 'skybind-android-debug-apks-unqualified'",
        "'m2-negative-live': 'negative-live'",
        "'m2-transport-live': 'transport-live'", "'m2-process-live': 'process-live'",
        'select_lanes(args.test)', 'live.current_source()',
        'live.github(args.run_id, sha)', 'live.verify_candidate(folder, args.run_id, sha, pin)',
        'installation_preflight(installed_identity(serial), manifest, pin)',
        "require(args.install, 'EXPLICIT_INSTALL_REQUIRED')",
        'live.installed_pair(serial, manifest, pin)',
        "install.add_argument('--install', action='store_true'",
        "p.add_argument('--test', action='append'",
        'execute_lane(lane, args.run_id, serial, folder, args.remote,',
        'root_grant_changed_by_runner=False, daemon_mutated=False',
        'device_qualified=False,', 'release_qualified=False,',
        'APK_PATH.fullmatch(path)', 'apk_manifest.apk_cert(dest)',
        "require(app['signer'] == pin and test['signer'] == pin",
        "'INCOMPLETE_HOSTED_APK_PAIR'", 'store_report(args.output_root, doc)',
    )
    for token in required:
        need(token in cli, 'CI_CLI_CONTRACT_MISSING_' + token[:65])
    for bad in ('--allow-source-mismatch', "['adb', 'shell', 'su'", 'os.system(',
                'shell=True', "'uninstall'", "'pm', 'clear'", "'reboot'",
                "'-d'", 'RootService.stop'):
        need(bad not in cli, 'CI_CLI_UNSAFE_' + bad)
    need('def run(opts):' in lane and "'skybind.live'" in lane and
         "'skybind.ui.live'" in lane and 'parse_ui_live(outcome.stdout)' in lane,
         'ISOLATED_LIVE_RUNNER_NOT_PRESERVED')
    need("report['receipt'] = str(filename)" in lane and
         "doc['receipt'] = store(doc)" in lane,
         'LIVE_RECEIPT_MUST_PERSIST_SELF_REFERENCE')
    need("doc.get('receipt') == receipt" in cli and
         "summary.get(field) == doc.get(field)" in cli and
         "m2_l1_device_qualified=False" in cli and
         "m2_l2_device_qualified=False" in cli and
         "'LANE_SCOPE_MISMATCH'" in cli,
         'HOST_LANE_RECEIPT_MUST_VERIFY_AND_DEFAULT_FALSE')
    need('def test_lane_preflight_saved_receipt_round_trip(' in tests and
         'def test_lane_missing_receipt_path_rejected(' in tests and
         'def test_lane_failed_result_is_preserved(' in tests,
         'LANE_RECEIPT_REGRESSIONS_MISSING')
    need('def test_other_signer_refused_before_install(' in tests and
         'def test_changed_pair_requires_explicit_install(' in tests and
         'def test_existing_pair_no_automatic_test_selection_or_install(' in tests,
         'CRITICAL_NEGATIVE_TESTS_MISSING')
    need('scripts/devtool/ci_artifacts_device_source_gate.py' in grouped and
         'scripts.devtool.test_ci_artifacts_device' in grouped,
         'GROUPED_SOURCE_INTEGRATION_MISSING')
    return {'state': 'PASS_SKYBIND_CI_ARTIFACTS_DEVICE_SOURCE_ONLY',
            'artifact_downloaded': False, 'apk_installed': False,
            'device_tested': False, 'release_qualified': False}

if __name__ == '__main__':
    try:
        print(json.dumps(verify(), sort_keys=True))
    except (Violation,OSError,UnicodeError) as exc:
        print(json.dumps({'state': 'FAILED_OR_BLOCKED', 'reason': str(exc)}, sort_keys=True))
        raise SystemExit(2)
