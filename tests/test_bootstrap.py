"""Executed negative/positive checks for the seed repository *plan* only."""
import copy
import unittest
from scripts.devtool.bootstrap_contract import check_all, check_component, load, TARGETS


class SkybindPlanningContracts(unittest.TestCase):
    def test_full_plan_contract(self):
        cfg, index = check_all()
        self.assertEqual(index["delivery_count"], 8)
        self.assertEqual(set(cfg["targets"]), TARGETS)

    def test_webui_copy_policy(self):
        self.assertIn("planning contract checked", check_component("webui"))

    def test_runtime_scope(self):
        self.assertIn("NOT certified", check_component("runtime"))

    def test_android_evidence_not_forged(self):
        self.assertIn("NOT certified", check_component("android"))

    def test_final_seal_unissued(self):
        _, index = load()
        self.assertIn(index["artifact_sequence"][-1]["status"], ("PLANNED", "SOURCE_IMPLEMENTED_NOT_PROMOTED"))
        self.assertIn("NOT certified", check_component("release"))

    def test_unknown_component_fail_closed(self):
        with self.assertRaises(ValueError):
            check_component("fake-release")


if __name__ == "__main__":
    unittest.main()
