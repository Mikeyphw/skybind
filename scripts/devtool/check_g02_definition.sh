#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
python3 -m unittest discover -s tests/gates -p 'test_g02*.py' -v
bash scripts/devtool/check_api_parity.sh
# Gate definition smoke test, not a milestone seal.
# Exit 3 + authentic BLOCKED JSON are mandatory at the current stage.
bash scripts/devtool/check_g02_state.sh
