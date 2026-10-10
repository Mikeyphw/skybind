#!/usr/bin/env bash
# Gate output is captured without filesystem side effects; never use /tmp.
set -euo pipefail
cd "$(dirname "$0")/../.."
gate_json=''
gate_rc=0
gate_json="$(python3 scripts/dev/gates/sb_g02.py --check)" || gate_rc=$?
printf '%s\n' "$gate_json"
# The expected result at this stage is an authentic BLOCKED gate (exit 3).
# An unexpected success, command error, or forged JSON fails validation.
if [ "$gate_rc" -ne 3 ]; then
  printf 'unexpected SB-G02 qualification exit code: %s\n' "$gate_rc" >&2
  exit 1
fi
printf '%s\n' "$gate_json" | python3 -c '
import json, sys
try:
    result = json.load(sys.stdin)
    valid = (isinstance(result, dict)
        and result.get("gate") == "SB-G02"
        and result.get("status") == "BLOCKED"
        and result.get("assurance") == "NOT_ATTESTED"
        and result.get("android_device") == "NOT_ATTESTED"
        and result.get("final_seal") == "NOT_ISSUED"
        and isinstance(result.get("reasons"), list)
        and len(result["reasons"]) > 0)
except (ValueError, TypeError):
    valid = False
if not valid:
    print("SB-G02 gate result is missing, malformed or not BLOCKED", file=sys.stderr)
    sys.exit(1)
'
