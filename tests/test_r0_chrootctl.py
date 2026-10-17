import importlib.util
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('ch_r0',ROOT/'scripts/dev/provider/chrootctl_r0.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

class ChrootSourceContract(unittest.TestCase):
    def test_closed_by_default(self):
        contract=mod.contract()
        self.assertFalse(contract['runtime_invocation_enabled'])
        self.assertEqual(contract['status'],'NOT_IMPLEMENTED')
    def test_exact_supported_command_names(self):
        self.assertEqual(set(mod.contract()['commands']),{'version','lsjson','cat','rcat','moveto','deletefile'})
    def test_immutable_required(self):
        self.assertIn('--immutable',mod.contract()['commands']['moveto']['flags'])
        self.assertIn('--stat',mod.contract()['commands']['lsjson']['flags'])
    def test_pinned_source_contract(self):
        self.assertIn('internal/rcloneops/stream.go',mod.contract()['sha256'])
        self.assertEqual(len(set(mod.contract()['sha256'].values())),len(mod.contract()['sha256']))
        self.assertTrue(all(__import__('hashlib').sha256((ROOT/'tests/fixtures/r0-consumers/chroot'/ (rel+'.fixture')).read_bytes()).hexdigest() == digest for rel,digest in mod.contract()['sha256'].items()))
        for value in mod.contract()['sha256'].values(): self.assertEqual(len(value),64)
    def test_declared_paths_pinned(self):
        available=set(mod.contract()['sha256'])
        for val in mod.contract()['commands'].values():
            for short in val['paths']:
                self.assertIn('internal/rcloneops/'+short,available)

if __name__=='__main__':unittest.main()
