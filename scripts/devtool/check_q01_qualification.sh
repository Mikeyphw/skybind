#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
python3 -m unittest discover -s tests/qualification -p 'test_q01_*.py' -v
python3 -m unittest discover -s tests/qualification -p 'test_personal_policy.py' -v
python3 -B scripts/dev/qualification/personal_policy.py check || [ "$?" -eq 3 ]
