#!/usr/bin/env bash
# Devtool automatic source/negative tests only. No CI dispatch or gate promotion.
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python3 -m unittest discover -s tests/qualification -p 'test_q03_*.py' -v
python3 -m py_compile scripts/dev/runtime/source_provenance.py
python3 - <<'PY'
import json,pathlib
lock=pathlib.Path('scripts/dev/runtime/source.lock.json')
data=json.loads(lock.read_text())
assert data['newfuture']['archive_sha256'] is None
assert all(data['bclone'][x] is None for x in ('commit','ndk_revision','go_version'))
assert not pathlib.Path('build/evidence/sb_g01_provider_builds.json').exists()
print('SB-Q03 SOURCE_ONLY_PASS; lock unapproved, G01-G08 BLOCKED, seal NOT_ISSUED')
PY
