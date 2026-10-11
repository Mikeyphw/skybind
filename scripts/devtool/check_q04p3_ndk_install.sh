#!/usr/bin/env bash
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python3 -m unittest discover -s tests/qualification -p 'test_q04p3_ndk_install.py' -v
python3 scripts/dev/runtime/pin_selection.py verify >/dev/null
python3 scripts/dev/runtime/source_build.py pins >/dev/null
printf '%s\n' 'SB-Q04P3 SOURCE_CONTRACT_PASS; NDK sdkmanager errors remain fatal, real independent builds NOT RUN; G01-G08 BLOCKED; seal NOT_ISSUED'
