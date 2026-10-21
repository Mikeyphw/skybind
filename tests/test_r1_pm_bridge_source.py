"""Source regressions for explicit R1 platform-only bridge, no device mutation."""
import importlib.util
import pathlib
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]

class BridgeSourceTests(unittest.TestCase):
    def test_contract(self):
        spec=importlib.util.spec_from_file_location('gate',ROOT/'scripts/dev/android/r1_pm_bridge_source_gate.py')
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.check(),0)
    def test_abstract_unix_fixture_handles_long_termux_tmpdir(self):
        fixture=(ROOT/'internal/brokeridentity/pm_bridge_test.go').read_text()
        self.assertIn('skybind-r1-pm-test-', fixture)
        self.assertIn('net.ListenUnix("unix", addr)', fixture)
        self.assertIn('nameSeed := sha256.Sum256([]byte(t.TempDir()))', fixture)
        self.assertIn('len(addr.Name) > 107', fixture)
        self.assertNotIn('filepath.Join(t.TempDir()', fixture)

    def test_android_hosted_only(self):
        workflow=(ROOT/'.github/workflows/skybind-r1-pm-bridge.yml').read_text()
        self.assertIn('GOOS: android',workflow)
        self.assertIn('source_sha',workflow)
        self.assertNotIn('release.qualified":true',workflow)
    def test_no_background_root_bridge(self):
        service=(ROOT/'module/service.sh').read_text()
        self.assertNotIn('r1-pm-bridge-check',service)
        self.assertNotIn('r1-pm-bridge-check',(ROOT/'module/post-fs-data.sh').read_text())
    def test_independent_user_pin(self):
        cli=(ROOT/'cmd/skybind-r1-pm/main.go').read_text()
        self.assertIn('skybind-context',cli)
        self.assertIn('skybind-uid',cli)
        self.assertIn('bkx-signer',cli)
        self.assertIn('ConsumerBrokerQualified bool',cli)
        self.assertNotIn('IssuedApproved(',cli)

if __name__=='__main__':unittest.main()
