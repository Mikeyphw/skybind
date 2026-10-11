#!/usr/bin/env bash
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python3 -m unittest discover -s tests/qualification -p 'test_q04p1_*.py' -v
python3 -m py_compile scripts/dev/runtime/skybind_runtime.py scripts/dev/runtime/source_build.py
python3 - <<'PY'
import json, pathlib
p=pathlib.Path('scripts/dev/runtime/source.lock.json')
lock=json.loads(p.read_text())
assert lock['newfuture']['archive_sha256'] is None
assert all(lock['bclone'][key] is None for key in ('commit','ndk_revision','go_version'))
print('SB-Q04P1 SOURCE CONTRACT ONLY: no pins promoted, independent builds NOT RUN; G01-G08 BLOCKED, final seal NOT_ISSUED')
PY
