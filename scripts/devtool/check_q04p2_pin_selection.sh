#!/usr/bin/env bash
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python3 -m unittest discover -s tests/qualification -p 'test_q04p2_*.py' -v
python3 -m py_compile scripts/dev/runtime/pin_selection.py scripts/dev/runtime/source_build.py
python3 scripts/dev/runtime/pin_selection.py verify
python3 scripts/dev/runtime/source_build.py pins
printf '%s\n' 'SB-Q04P2 SELECTED_INPUTS_UNATTESTED: NewFuture prebuilt retained, no external signatures/build receipts/device gates; G01-G08 BLOCKED, final seal NOT_ISSUED'
