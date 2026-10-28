"""Executed negative/positive checks for the seed repository *plan* only."""
import copy
import unittest
from scripts.devtool.bootstrap_contract import check_all, check_component, load, TARGETS
from scripts.devtool.typed_catalog_contract import validate_live_catalog
from pathlib import Path
import json


class SkybindPlanningContracts(unittest.TestCase):
    def test_full_plan_contract(self):
        cfg, index = check_all()
        self.assertEqual(index["delivery_count"], 8)
        self.assertEqual(set(cfg["targets"]), TARGETS)

    def test_only_approved_native_extensions(self):
        root = Path(__file__).resolve().parents[1]
        old, live = validate_live_catalog(root)
        self.assertEqual(len(old), 57)
        self.assertEqual(len(live), 59)

    def test_extra_operation_fails_closed(self):
        root = Path(__file__).resolve().parents[1]
        data = json.loads((root/'internal/control/operations.json').read_text())
        data['operations'].append({**data['operations'][-1], 'name': 'shell.exec'})
        data['total'] += 1
        with self.assertRaisesRegex(AssertionError, 'UNAPPROVED_CATALOG_OPERATION'):
            validate_live_catalog(root, live=data)

    def test_extension_provenance_drift_fails_closed(self):
        root = Path(__file__).resolve().parents[1]
        data = json.loads((root/'internal/control/operations.json').read_text())
        item = next(x for x in data['operations'] if x['name']=='mount.stop.guarded')
        item['operation_class'] = 'query'
        with self.assertRaisesRegex(AssertionError, 'APPROVED_EXTENSION_DRIFT'):
            validate_live_catalog(root, live=data)

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
