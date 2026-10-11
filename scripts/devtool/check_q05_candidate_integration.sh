#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
python3 -m unittest discover -s tests/qualification -p 'test_q05_candidate_integration.py' -v
python3 -m unittest discover -s tests/qualification -p 'test_q05p2_cross_compile_ci.py' -v
python3 -m unittest discover -s tests/fault -p 'test_release_faults.py' -v
python3 scripts/dev/runtime/pin_selection.py verify
bash scripts/devtool/check_q04p3_ndk_install.sh
printf '%s\n' 'SB-Q05P1 SOURCE_ONLY_PASS; Q04 input binding and candidate integration exercised, no real device test, G01-G08 BLOCKED; final seal NOT_ISSUED'
