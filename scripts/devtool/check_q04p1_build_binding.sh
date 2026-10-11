#!/usr/bin/env bash
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python3 -m unittest discover -s tests/qualification -p 'test_q04p1_*.py' -v
python3 -m py_compile scripts/dev/runtime/skybind_runtime.py scripts/dev/runtime/source_build.py
python3 scripts/dev/runtime/pin_selection.py verify
echo 'SB-Q04P1 exact binary reuse PASS; selected inputs do not attest any G01 gate; G01-G08 BLOCKED, final seal NOT_ISSUED'
