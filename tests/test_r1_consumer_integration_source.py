import importlib.util
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
class R1IntegrationSource(unittest.TestCase):
    def test_full_gate(self):
        p=ROOT/'scripts/dev/android/r1_consumer_integration_source_gate.py'
        s=importlib.util.spec_from_file_location('source_gate',p)
        m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
        self.assertEqual(m.gate(),0)
    def test_no_autostart_or_external_qualification(self):
        assert not any('skybind-r1-gateway' in (ROOT/p).read_text() for p in ('module/service.sh','module/post-fs-data.sh'))
        import json
        a=json.loads((ROOT/'docs/contracts/rclone-compat/SKYBIND_CONSUMER_ABI_V1.json').read_text())
        self.assertEqual(a['external_transport_status'],'NOT_IMPLEMENTED')
        self.assertEqual(a['available_external_capabilities'],[])
    def test_token_not_logged_by_operator(self):
        op=(ROOT/'cmd/skybind-r1-gateway/main.go').read_text()
        self.assertNotIn('fmt.Println(token)',op)
        self.assertNotIn('log.Printf',op)
        self.assertIn('RevokeIssued',op)
if __name__=='__main__':unittest.main()
