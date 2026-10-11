#!/usr/bin/env bash
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python3 -m unittest discover -s tests/qualification -p 'test_q03r1_*.py' -v
python3 -m py_compile scripts/dev/runtime/pin_review.py
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('scripts/dev/runtime/source.lock.json')
v=json.loads(p.read_text())
assert v['newfuture']['archive_sha256'] is None
assert all(v['bclone'][n] is None for n in ('commit','go_version','ndk_revision'))
print('SB-Q03R1 SOURCE_ONLY_PASS; Go 1.27.2 selected; all trust pins NULL, G01-G08 BLOCKED, final seal NOT_ISSUED')
PY
