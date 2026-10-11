#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
python3 -m unittest discover -s tests/qualification -p 'test_q05p5_webui_runtime.py' -v
printf '%s\n' 'SB-Q05P5 WEBUI SOURCE_ONLY_PASS: native failure reason displayed, no device gate or release seal asserted'
