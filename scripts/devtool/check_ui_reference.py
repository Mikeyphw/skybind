#!/usr/bin/env python3
"""Read-only imported UI hash/DOM verifier (not visual parity proof)."""
import subprocess, sys
from pathlib import Path
root = Path(__file__).resolve().parents[2]
result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests/contracts", "-p", "test_*.py", "-v"], cwd=root, check=False)
raise SystemExit(result.returncode)
