"""Require bounded native-Termux Go regression without weakening milestone gates.

The Go runner's package count is selected through its target-local resource
policy. The full regression remains a required independent child of the release
workflow. The fast contract gate must not imply complete Go qualification.
"""
import pathlib
import tomllib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class TermuxGoRunnerPolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = tomllib.loads((ROOT / '.devtool.toml').read_text())

    def test_native_go_target_is_serial_and_still_native(self):
        target = self.cfg['targets']['skybind_go']
        self.assertEqual(target['runner'], 'go')
        self.assertEqual(target['go']['max_workers'], 1)
        self.assertEqual(target['workflows']['test'], ['runner:go#test'])

    def test_full_regression_retains_all_dependencies(self):
        release = self.cfg['targets']['skybind_release']['workflows']
        full = release['r1-full-regression']
        refs = {node['ref'] for node in full}
        self.assertEqual(refs, {
            'target:skybind_release#r1-transport-source',
            'target:skybind_go#isolated-regression',
        })
        transport = release['r1-transport-source']
        self.assertEqual({node['ref'] for node in transport}, {
            'target:skybind_release#r1-source',
            'target:skybind_api_contracts#r1-transport',
            'target:skybind_android_app#build-policy',
        })
        fast = release['r1-source']
        fast_refs = {node['ref'] for node in fast}
        self.assertNotIn('target:skybind_go#test', fast_refs)
        self.assertEqual(fast_refs, {
            'target:skybind_release#r0-compat',
            'target:skybind_api_contracts#r1-policy',
        })

    def test_original_go_runner_retained_for_diagnostics(self):
        workflows = self.cfg['targets']['skybind_release']['workflows']
        self.assertEqual(workflows['r1-go-runner-diagnostic'][0]['ref'],
                         'target:skybind_go#test')
        go = self.cfg['targets']['skybind_go']
        self.assertEqual(go['workflows']['isolated-regression'],
                         ['job:isolated-regression'])

    def test_r1_transport_broker_not_activated(self):
        ipc = ROOT / 'internal/brokeripc/server.go'
        self.assertTrue(ipc.is_file())
        text = ipc.read_text()
        self.assertIn('SO_PEERCRED', text)
        self.assertNotIn('net.Listen(', text)
        self.assertNotIn('net.ListenUnix(', text)
        job = self.cfg['targets']['skybind_api_contracts']['jobs']['r1-transport']
        self.assertFalse(job['metadata']['production_listener_enabled'])
        self.assertIn('./internal/brokeripc', job['command'])

    def test_cloud_only_android_policy_preserved(self):
        android = ROOT / '.github/workflows/skybind-android-apks.yml'
        self.assertTrue(android.is_file())
        script = ROOT / 'scripts/dev/android/verify_cloud_build_only.py'
        self.assertTrue(script.is_file())


if __name__ == '__main__':
    unittest.main()
