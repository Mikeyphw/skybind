from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/devtool/api05_personal_device.py"
spec = importlib.util.spec_from_file_location("skybind_api05_personal", SCRIPT)
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


def fixture(stage="gateway", **kwargs):
    base = {
        "schema": a.SCHEMA, "stage": stage, "device_qualification_complete": False,
        "environment": {"android": True, "root_available": True, "selinux": "Enforcing", "boot_id": "boot1"},
        "policy": {k: {"observed": True, "secure": True} for k in ("parent", "query", "mutation")},
        "sockets": {k: {"reachable": True, "root_peer": True, "denial": "pass"} for k in ("query", "mutation")},
        "mount": {"observed": True, "mounted": True},
    }
    base.update(kwargs)
    return base


class PersonalDeviceEvidence(unittest.TestCase):
    def test_negative_sockets_never_claim_positive_acceptance(self):
        got = a.gate_results([fixture()])
        self.assertEqual(got["gates"]["05-2-gateway"], "PARTIAL")
        self.assertEqual(got["gates"]["05-4-final-seal"], "BLOCKED")
        self.assertFalse(got["device_qualification_complete"])

    def test_nonroot_server_is_blocked(self):
        s = fixture()
        s["sockets"]["mutation"]["root_peer"] = False
        result = a.gate_results([s])
        self.assertEqual(result["gates"]["05-2-gateway"], "BLOCKED")
        self.assertIn("nonroot_server_socket:mutation", result["observations"]["security_blockers"])

    def test_unavailable_policy_never_passes(self):
        s = fixture()
        s["policy"]["query"]["secure"] = False
        self.assertEqual(a.gate_results([s])["gates"]["05-1-security"], "BLOCKED")

    def test_permissive_android_never_qualifies_security(self):
        s = fixture()
        s["environment"]["selinux"] = "Permissive"
        self.assertEqual(a.gate_results([s])["gates"]["05-1-security"], "BLOCKED")

    def test_not_android_never_qualifies(self):
        s = fixture()
        s["environment"]["android"] = False
        self.assertEqual(a.gate_results([s])["gates"]["05-1-security"], "BLOCKED")

    def test_mutation_socket_absent_not_false_pass(self):
        s = fixture()
        s["sockets"]["mutation"]["reachable"] = False
        self.assertEqual(a.gate_results([s])["gates"]["05-2-gateway"], "NOT_RUN")

    def test_reboot_needs_changed_boot_id_and_mount_observation(self):
        baseline = fixture(stage="baseline")
        reboot = fixture(stage="after_reboot")
        self.assertEqual(a.gate_results([baseline,reboot])["gates"]["05-3-lifecycle"], "NOT_RUN")
        reboot["environment"]["boot_id"] = "boot2"
        self.assertEqual(a.gate_results([baseline,reboot])["gates"]["05-3-lifecycle"], "PARTIAL")
        self.assertEqual(a.gate_results([baseline,reboot])["gates"]["05-4-final-seal"], "BLOCKED")

    def test_forged_final_seal_fails_closed(self):
        s = fixture(device_qualification_complete=True)
        with self.assertRaisesRegex(ValueError, "forged"):
            a.gate_results([s])

    def test_unknown_schema_fails_closed(self):
        with self.assertRaises(ValueError):
            a.gate_results([fixture(schema="wrong")])

    def test_no_mountpoint_is_not_mount_evidence(self):
        self.assertFalse(a.mount_snapshot(None)["observed"])
        with self.assertRaises(ValueError):
            a.mount_snapshot("relative/path")

    def test_policy_stats_requires_exact_root_owner_mode_and_type(self):
        with patch.object(a, "root_command", return_value={"ok": True, "stdout": "0 600 1 regular file", "code": 0}):
            self.assertTrue(a.inspect_secure_file(a.POLICIES["query"])["secure"])
        with patch.object(a, "root_command", return_value={"ok": True, "stdout": "0 644 1 regular file", "code": 0}):
            self.assertFalse(a.inspect_secure_file(a.POLICIES["query"])["secure"])
        with patch.object(a, "root_command", return_value={"ok": True, "stdout": "0 600 1 symbolic link", "code": 0}):
            self.assertFalse(a.inspect_secure_file(a.POLICIES["query"])["secure"])

    def test_negative_probe_refuses_same_uid(self):
        fake = object()
        with patch.object(a.socket, "socket") as make, patch.object(a.os, "getuid", return_value=12345):
            sock = make.return_value.__enter__.return_value
            sock.getsockopt.return_value = __import__("struct").pack("3i", 42, 0, 0)
            result = a.probe_socket(a.QUERY, 12345, send_denial=True)
            self.assertEqual(result["denial"], "blocked_same_uid_as_approved")
            sock.sendall.assert_not_called()

    def test_atomic_output_is_private_and_no_symlink_follow(self):
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / "result.json"
            a.atomic_json(path, {"a": 1})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(path.read_text())["a"], 1)
            alias = Path(t) / "alias.json"
            alias.symlink_to(path)
            with self.assertRaises(ValueError):
                a.atomic_json(alias, {"a": 2})

    def test_invalid_uid_rejected_before_probe(self):
        with tempfile.TemporaryDirectory() as t:
            path = str(Path(t) / "out.json")
            self.assertEqual(a.main(["capture", "--stage", "gateway", "--output", path, "--probe-unapproved-client"]), 2)
            self.assertEqual(a.main(["capture", "--stage", "gateway", "--output", path, "--approved-consumer-uid", "1"]), 2)
            self.assertFalse(Path(path).exists())

    def test_evaluate_cli_never_seals(self):
        with tempfile.TemporaryDirectory() as t:
            inp, out = Path(t)/"e.json", Path(t)/"report.json"
            inp.write_text(json.dumps(fixture()))
            self.assertEqual(a.main(["evaluate", "--output", str(out), str(inp)]), 0)
            self.assertEqual(json.loads(out.read_text())["gates"]["05-4-final-seal"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
