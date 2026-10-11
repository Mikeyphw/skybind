#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
python3 -m unittest discover -s tests/qualification -p 'test_q05p7_local_wrapper.py' -v
python3 -m unittest discover -s tests/qualification -p 'test_q05_candidate_integration.py' -v
printf '%s\n' 'SB-Q05P7 LOCAL WRAPPER CONTRACT PASS; local candidates remain unqualified, all gates BLOCKED, seal NOT_ISSUED'
