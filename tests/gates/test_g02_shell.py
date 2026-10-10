import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "scripts/devtool/check_g02_state.sh"

class G02GateShellPortability(unittest.TestCase):
    def test_real_gate_runs_without_writable_tmp(self):
        env = dict(os.environ, TMPDIR="/dev/null")
        completed = subprocess.run(["bash", str(HELPER)], cwd=ROOT, env=env,
                                   capture_output=True, text=True, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["final_seal"], "NOT_ISSUED")

    def _fixture(self, payload, exit_code):
        with tempfile.TemporaryDirectory(prefix="sb-g02-regression-") as folder:
            root = Path(folder)
            bin_dir = root / "scripts/devtool"
            gate_dir = root / "scripts/dev/gates"
            bin_dir.mkdir(parents=True)
            gate_dir.mkdir(parents=True)
            shutil.copyfile(HELPER, bin_dir / "check_g02_state.sh")
            (gate_dir / "sb_g02.py").write_text(
                "import sys\nprint(" + repr(payload) + ")\nsys.exit(" + str(exit_code) + ")\n"
            )
            env = dict(os.environ, TMPDIR="/dev/null")
            return subprocess.run(["bash", str(bin_dir / "check_g02_state.sh")], cwd=root,
                                  env=env, capture_output=True, text=True, timeout=10)

    def test_blocked_is_accepted_only_with_matching_exit_code(self):
        payload = json.dumps({"gate":"SB-G02","status":"BLOCKED", "assurance":"NOT_ATTESTED",
                              "android_device":"NOT_ATTESTED", "final_seal":"NOT_ISSUED",
                              "reasons":["SB-G01 is not source-qualified"]})
        self.assertEqual(self._fixture(payload, 3).returncode, 0)
        for wrong_exit in (0, 1, 2):
            with self.subTest(exit_code=wrong_exit):
                self.assertNotEqual(self._fixture(payload, wrong_exit).returncode, 0)

    def test_false_green_and_malformed_payloads_fail_closed(self):
        forged = json.dumps({"gate":"SB-G02", "status":"SOURCE_CONTROL_PASS",
                             "assurance":"SOURCE_ONLY", "android_device":"NOT_ATTESTED",
                             "final_seal":"NOT_ISSUED", "reasons":[]})
        for payload in (forged, "not-json", "{}", "[]", ""):
            with self.subTest(payload=payload[:20]):
                self.assertNotEqual(self._fixture(payload, 3).returncode, 0)

if __name__ == "__main__":
    unittest.main()
