#!/usr/bin/env python3
"""Read-only chrootctl source contract verification; never launches rclone."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / 'docs/contracts/rclone-compat/R0_CHROOTCTL_SOURCE_SHA256.json'

def contract():
    value = json.loads(MANIFEST.read_text())
    if value['schema_version'] != 1 or value['status'] != 'NOT_IMPLEMENTED' or value['runtime_invocation_enabled'] is not False:
        raise ValueError('R0 must not enable execution')
    return value

def audit_source(root: Path):
    c=contract()
    return [key for key, expected in sorted(c['sha256'].items()) if not (root/key).is_file() or hashlib.sha256((root/key).read_bytes()).hexdigest() != expected]

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--audit-source',type=Path)
    ns=ap.parse_args()
    c=contract()
    missing=audit_source(ns.audit_source) if ns.audit_source else []
    print(json.dumps({'status':'PASS_R0_SOURCE_CONTRACT' if not missing else 'FAIL_SOURCE_DRIFT','runtime_qualified':False,'source_audited':bool(ns.audit_source),'mismatches':missing,'commands':sorted(c['commands'])},sort_keys=True))
    return 0 if not missing else 2

if __name__=='__main__': raise SystemExit(main())
