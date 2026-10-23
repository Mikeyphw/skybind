#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
python3 -m unittest discover -s tests/gates -p 'test_g02*.py' -v
python3 -m unittest discover -s tests/qualification -p 'test_personal_policy.py' -v
bash scripts/devtool/check_api_parity.sh
bash scripts/devtool/check_g02_state.sh
