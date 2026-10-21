import importlib.util
from pathlib import Path
import unittest
import tomllib
ROOT=Path(__file__).resolve().parents[1]
class R1IntegrationSource(unittest.TestCase):
    def test_full_gate(self):
        p=ROOT/'scripts/dev/android/r1_consumer_integration_source_gate.py'
        s=importlib.util.spec_from_file_location('source_gate',p)
        m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
        self.assertEqual(m.gate(),0)
    def test_release_target_commands_resolve_from_release_directory(self):
        p = ROOT / 'scripts/dev/android/r1_consumer_integration_source_gate.py'
        spec = importlib.util.spec_from_file_location('integration_gate_cwd', p)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        config = tomllib.loads((ROOT / '.devtool.toml').read_text())
        checks = module.release_target_cwd_checks(config, ROOT)
        self.assertTrue(all(checks.values()), checks)
        # Mutation tests: each original working-directory defect must FAIL.
        from copy import deepcopy
        jobs = config['targets']['skybind_release']['jobs']
        for job, bad_command in (
            ('r1-consumer-integration-contract',
                ['python3', '-B', 'scripts/dev/android/r1_consumer_integration_source_gate.py']),
            ('r1-consumer-integration-go',
                ['go', 'test', '-count=1', './internal/brokerruntime']),
            ('r1-consumer-transport-go',
                ['go', 'test', '-count=1', './internal/brokeripc']),
        ):
            mutated = deepcopy(config)
            mutated['targets']['skybind_release']['jobs'][job]['command'] = bad_command
            self.assertFalse(all(module.release_target_cwd_checks(mutated, ROOT).values()), job)

    def test_hosted_authority_apk_owner_validation_not_skipped(self):
        workflow=(ROOT/'.github/workflows/skybind-r1-consumer-diagnostics.yml').read_text()
        source=(ROOT/'internal/brokeridentity/authority_apk_test.go').read_text()
        # The unprivileged CI lane must exercise the reject-untrusted-owner
        # test; the root lane must positively run, and prove PASS rather than
        # merely succeed with a skipped APK ownership test.
        self.assertIn('TestAuthorityAPKUnprivilegedOwnerIsRejected', source)
        self.assertIn('os.Geteuid() != 0', source)
        self.assertIn('t.Skip("requires a root-owned APK fixture', source)
        self.assertIn("-run '^TestAuthorityAPKExactApprovedBytesAndMutation$'", workflow)
        self.assertIn('sudo env PATH="$PATH" go test -count=1 -v', workflow)
        self.assertIn('--- PASS: TestAuthorityAPKUnprivilegedOwnerIsRejected', workflow)
        self.assertIn('--- PASS: TestAuthorityAPKExactApprovedBytesAndMutation', workflow)
        self.assertIn('go test -count=1 ./internal/brokeridentity', workflow)

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
