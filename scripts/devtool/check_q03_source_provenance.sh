#!/usr/bin/env bash
# Devtool automatic source/negative tests only. No CI dispatch or gate promotion.
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python3 -m unittest discover -s tests/qualification -p 'test_q03_*.py' -v
python3 -m py_compile scripts/dev/runtime/source_provenance.py
python3 scripts/dev/runtime/pin_selection.py verify
echo 'SB-Q03 regression remains RAW_UNATTESTED; selected CI inputs do not attest provenance; G01-G08 BLOCKED, final seal NOT_ISSUED'
