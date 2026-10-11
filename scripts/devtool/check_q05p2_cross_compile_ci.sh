#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
python3 -m unittest discover -s tests/qualification -p 'test_q05p2_cross_compile_ci.py' -v
python3 -m unittest discover -s tests/qualification -p 'test_q05_candidate_integration.py' -v
python3 scripts/dev/runtime/pin_selection.py verify
printf '%s\n' 'SB-Q05P2 SOURCE_ONLY_PASS: native Linux tests separated from Android cross-build; real CI rerun and device qualification pending; G01-G08 BLOCKED; SEAL NOT_ISSUED'
