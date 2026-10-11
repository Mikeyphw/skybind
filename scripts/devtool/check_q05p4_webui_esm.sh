#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
command -v node >/dev/null
for source in module/webroot/*.js; do
  test -f "$source"
  node --input-type=module --check < "$source"
done
python3 -m unittest discover -s tests/qualification -p 'test_q05p4_webui_esm.py' -v
printf '%s\n' 'SB-Q05P4 ESM_PARSE_PASS (SOURCE ONLY): bootstrap syntax repaired; device WebView NOT QUALIFIED; G01-G08 BLOCKED; SEAL NOT_ISSUED'
