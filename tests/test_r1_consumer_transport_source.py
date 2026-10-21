"""Offline gates: read-only R1 transport remains separately qualified from PM."""
import importlib.util
import pathlib
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]

class R1TransportSourceTests(unittest.TestCase):
    def test_source_gate(self):
        path=ROOT/'scripts/dev/android/r1_consumer_transport_source_gate.py'
        spec=importlib.util.spec_from_file_location('r1_transport_gate',path)
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.check(),0)

    def test_no_module_auto_start_or_override(self):
        startup='\n'.join((ROOT/name).read_text() for name in ('module/service.sh','module/post-fs-data.sh'))
        self.assertNotIn('StartAbstract',startup)
        self.assertNotIn('skybind-r1-consumer-gateway-v1',startup)
        self.assertIn('ConsumerAbstractEndpoint', (ROOT/'internal/brokeripc/client.go').read_text())

    def test_existing_one_authority_grants(self):
        gateway=(ROOT/'internal/brokerruntime/gateway.go').read_text()
        abstract=(ROOT/'internal/brokeripc/abstract.go').read_text()
        self.assertIn('brokergrant.New()',gateway)
        self.assertIn('Verifier: verifier',gateway)
        self.assertIn('Grants: grants',gateway)
        self.assertIn('pm.State() != "CONNECTED_UNQUALIFIED"',gateway)
        self.assertNotIn('IssueApproved(',abstract)

    def test_client_does_not_change_bkx_or_chrootctl(self):
        client=(ROOT/'internal/brokeripc/client.go').read_text()
        self.assertIn('CloseWrite()',client)
        for word in ['exec.Command','rclone copy','--config','--retries','deletefile']:
            self.assertNotIn(word,client)

if __name__ == '__main__':unittest.main()
