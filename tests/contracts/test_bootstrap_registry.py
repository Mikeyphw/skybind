"""Only explicitly adopted Devtool targets may enter source bootstrap."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/devtool'))
import bootstrap_contract as bootstrap


class AdoptedTargetBootstrapContract(unittest.TestCase):
    def _with_targets(self, change):
        cfg, plan = bootstrap.load()
        cfg = deepcopy(cfg)
        change(cfg['targets'])
        with patch.object(bootstrap, 'load', return_value=(cfg, plan)):
            return bootstrap.check_all()

    def test_current_adopted_targets_validate_without_sealing(self):
        _, _ = bootstrap.check_all()
        self.assertIn('NOT certified', bootstrap.check_component('release').replace('NOT certified', 'NOT certified'))

    def test_unknown_target_is_not_silently_accepted(self):
        def add_unreviewed(targets):
            targets['skybind_unreviewed'] = deepcopy(targets['skybind_go'])
        with self.assertRaises(AssertionError):
            self._with_targets(add_unreviewed)

    def test_original_bootstrap_cannot_disappear(self):
        with self.assertRaises(AssertionError):
            self._with_targets(lambda targets: targets['skybind_android_device']['workflows'].pop('bootstrap'))

    def test_new_product_workflows_must_be_routable(self):
        with self.assertRaises(AssertionError):
            self._with_targets(lambda targets: targets['skybind_go']['workflows'].update({'test':['not-a-job']}))


if __name__ == '__main__':
    unittest.main()
