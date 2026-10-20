"""M3 negative contract, source-only; not a simulation of real root or job writes."""
import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

gate = load('m3_gate', 'scripts/dev/android/m3_operations_source_gate.py')
runner = load('m3_runner', 'scripts/dev/android/m2_live_device.py')
ci = load('m3_ci', 'scripts/devtool/ci_artifacts_device.py')
GOOD = '''INSTRUMENTATION_STATUS: class=io.github.mikeyphw.skybind.LiveM3PreviewAcceptanceTest
INSTRUMENTATION_STATUS: numtests=1
INSTRUMENTATION_STATUS: test=liveM3ReadOnlyJobPreview
INSTRUMENTATION_STATUS_CODE: 1
INSTRUMENTATION_STATUS: test=liveM3ReadOnlyJobPreview
INSTRUMENTATION_STATUS_CODE: 0
INSTRUMENTATION_RESULT: stream=OK (1 test)
INSTRUMENTATION_CODE: -1
'''

class M3Regressions(unittest.TestCase):
    def test_current_source_gate(self):
        self.assertEqual(gate.verify(ROOT)['state'], 'PASS_M3_CONSOLIDATED_OPERATIONS_SOURCE_ONLY')

    def test_preview_acceptance_exact_one_case(self):
        self.assertEqual(runner.parse_m3_preview(GOOD), ('PASS_M3_REAL_DAEMON_PREVIEW_ONLY', None))
        for invalid in (GOOD.replace('numtests=1', 'numtests=2'),
                        GOOD.replace('STATUS_CODE: 0', 'STATUS_CODE: -2'),
                        GOOD.replace('INSTRUMENTATION_CODE: -1', ''),
                        GOOD.replace('liveM3ReadOnlyJobPreview', 'unrecognizedCase'),
                        GOOD + 'INSTRUMENTATION_STATUS_CODE: 0\n',
                        GOOD + 'FAILURES!!!\n'):
            with self.subTest(invalid=invalid[-40:]):
                self.assertEqual(runner.parse_m3_preview(invalid)[0], 'FAILED')

    def test_preview_skips_and_missing_fixture_never_pass(self):
        for marker in runner.M3_BLOCKED:
            self.assertEqual(runner.parse_m3_preview(GOOD + marker), ('BLOCKED', marker))
        self.assertEqual(runner.parse_m3_preview(GOOD + 'INSTRUMENTATION_STATUS_CODE: -3\n')[0], 'BLOCKED')

    def test_preview_security_failures_not_promoted(self):
        for marker in runner.M3_FAILED:
            self.assertEqual(runner.parse_m3_preview(GOOD + marker), ('FAILED', marker))

    def test_new_lane_is_opt_in_only(self):
        self.assertEqual(ci.select_lanes([]), [])
        self.assertEqual(ci.select_lanes(['m3-preview-live']), ['m3-preview-live'])
        with self.assertRaisesRegex(ci.QualificationError, 'UNKNOWN_TEST_LANE'):
            ci.select_lanes(['m3-job-run-live'])

    def test_preview_receipt_scoped(self):
        base = dict(schema='skybind-m2-live-v1', source_sha='a'*40, github_run_id=2,
            artifact_id=7, installed_pair_verified=True, signing_verified=True,
            device_qualified=False, release_qualified=False,
            m2_l1_device_qualified=False, m2_l2_device_qualified=False,
            m2_l3_negative_device_qualified=False,
            m2_l3_transport_device_qualified=False,
            m2_l3_process_device_qualified=False,
            m3_preview_device_qualified=True,
            state='PASS_M3_REAL_DAEMON_PREVIEW_ONLY',
            qualified_scope='M3_REAL_DAEMON_JOB_PREVIEW_ONLY_NO_EXECUTION')
        self.assertEqual(ci.validated_lane_receipt(base, lane='m3-preview-live',
                         run_id=2, sha='a'*40, artifact_id=7)['state'], base['state'])
        for corruption in ({'m2_l3_transport_device_qualified': True},
                           {'m3_preview_device_qualified': False},
                           {'qualified_scope': 'M3_ALL'},
                           {'source_sha':'b'*40}, {'release_qualified': True},
                           {'state':'BLOCKED'}):
            with self.subTest(corruption=corruption):
                with self.assertRaises(ci.QualificationError):
                    ci.validated_lane_receipt({**base, **corruption},
                        lane='m3-preview-live',run_id=2,sha='a'*40,artifact_id=7)

    def mutate(self, relative, old, new):
        with tempfile.TemporaryDirectory(prefix='skybind-m3-negative-') as d:
            target=Path(d)
            for rel in [*gate_relevant_files()]:
                src=ROOT/rel; dest=target/rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src,dest)
            p=target/relative
            content=p.read_text()
            self.assertIn(old,content)
            p.write_text(content.replace(old,new,1))
            with self.assertRaises(gate.Violation):gate.verify(target)

    def test_reject_implicit_job_start(self):
        self.mutate('android-app/app/src/main/java/io/github/mikeyphw/skybind/bridge/SkybindSessionViewModel.kt',
            'fun connect() {', 'fun connect() {\n        bridge.startPreparedJob(preparedJob!!)')

    def test_reject_unowned_cancellation(self):
        self.mutate('android-app/app/src/main/java/io/github/mikeyphw/skybind/bridge/RootReadBridgeService.kt',
            'ownedRuns[runId] != session', 'false')

    def test_reject_delayed_preview_after_disconnect(self):
        self.mutate('android-app/app/src/main/java/io/github/mikeyphw/skybind/bridge/RootReadBridgeService.kt',
            'if (session in forgottenSessions)', 'if (false)')

    def test_reject_resurrected_session_ownership(self):
        self.mutate('android-app/app/src/main/java/io/github/mikeyphw/skybind/bridge/RootReadBridgeService.kt',
            'if (session !in liveSessions)', 'if (false)')

    def test_reject_replayed_ticket(self):
        self.mutate('android-app/app/src/main/java/io/github/mikeyphw/skybind/bridge/RootReadBridgeService.kt',
            'tickets.remove(previewId)', 'tickets[previewId]')

    def test_reject_destructive_sync_enablement(self):
        self.mutate('android-app/app/src/main/java/io/github/mikeyphw/skybind/bridge/RootReadBridgeService.kt',
            'kind !in setOf("check", "copy")', 'kind !in setOf("check", "copy", "sync")')

    def test_reject_proof_in_ui_output(self):
        self.mutate('android-app/app/src/main/java/io/github/mikeyphw/skybind/bridge/RootReadBridgeService.kt',
            '.put("source", source).put("destination", destination).toString()',
            '.put("source", source).put("proof", proof).put("destination", destination).toString()')

    def test_reject_preview_test_execution(self):
        self.mutate('android-app/app/src/androidTest/java/io/github/mikeyphw/skybind/LiveM3PreviewAcceptanceTest.kt',
            'session.previewJob(selected.name)', 'session.startPreparedJob(selected.name)')

    def test_reject_double_autotest(self):
        self.assertNotIn('m3-job-run-live', ci.LANES)
        self.assertFalse(gate.verify(ROOT)['write_job_device_qualified'])


def gate_relevant_files():
    src=__import__('inspect').getsource(gate.verify)
    # Gate reads only these 11 source files + one Devtool TOML.
    base=Path('android-app/app/src/main/java/io/github/mikeyphw/skybind')
    return [base/'bridge/RootReadBridgeService.kt',base/'bridge/RootReadSession.kt',
        base/'bridge/SkybindSessionViewModel.kt',base/'ui/SkybindApp.kt',
        base/'model/SkybindReadModel.kt',base/'bridge/LiveReadSnapshotReader.kt',
        base/'MainActivity.kt',
        Path('android-app/app/src/main/aidl/io/github/mikeyphw/skybind/bridge/IRootReadBridge.aidl'),
        Path('android-app/app/src/androidTest/java/io/github/mikeyphw/skybind/LiveM3PreviewAcceptanceTest.kt'),
        Path('scripts/dev/android/m2_live_device.py'),
        Path('scripts/devtool/ci_artifacts_device.py'),Path('.devtool.toml')]

if __name__ == '__main__':unittest.main()
