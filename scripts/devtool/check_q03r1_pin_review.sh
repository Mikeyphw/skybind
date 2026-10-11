#!/usr/bin/env bash
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python3 -m unittest discover -s tests/qualification -p 'test_q03r1_*.py' -v
python3 -m py_compile scripts/dev/runtime/pin_review.py
python3 scripts/dev/runtime/pin_selection.py verify
echo 'SB-Q03R1 historical raw replay remains UNATTESTED; selected pins do not change custody; G01-G08 BLOCKED, final seal NOT_ISSUED'
