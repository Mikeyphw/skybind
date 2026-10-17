#!/usr/bin/env python3
"""Offline R0 contract inspection. NEVER runs rclone, network or mutations."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve()
CONTRACT = HERE.parents[3] / 'docs/contracts/rclone-compat/R0_BKX_CLI_MATRIX.json'
MANIFEST = HERE.parents[3] / 'docs/contracts/rclone-compat/R0_BKX_SOURCE_SHA256.json'
SAFE_NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$')


def load_contract(path=CONTRACT):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data['schema_version'] != 1 or data['status'] != 'NOT_IMPLEMENTED':
        raise ValueError('R0 contract must remain NOT_IMPLEMENTED')
    if data['constraints']['runtime_invocation_enabled'] is not False:
        raise ValueError('R0 invocation must remain disabled')
    return data


def remote_location(value: str) -> bool:
    """Conservatively inspect a future rclone remote path; NEVER authorize it."""
    if not isinstance(value, str) or not value or len(value) > 4096:
        return False
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        return False
    if '\\' in value or '%' in value or '?' in value or '#' in value:
        return False
    if value.startswith('rclone://'):
        tail = value[9:]
        parts = tail.split('/', 1)
        if len(parts) != 2 or not SAFE_NAME.fullmatch(parts[0]):
            return False
        path = parts[1]
    elif ':' in value:
        remote, path = value.split(':', 1)
        if not SAFE_NAME.fullmatch(remote):
            return False
    else:
        # No automatic access to local files from a future privileged process.
        return False
    if path.startswith('/') or path.startswith('~'):
        return False
    # Includes path-escaping relative components (no normalization before check).
    return all(part not in ('.', '..') for part in path.split('/'))


def inspect(argv, contract=None):
    """Return a redacted classification. Successful syntax is NOT execution permission."""
    contract = contract or load_contract()
    if not argv:
        return {'status': 'DENY', 'reason': 'EMPTY_COMMAND'}
    command = argv[0]
    spec = contract['commands'].get(command)
    if spec is None:
        return {'status': 'DENY', 'reason': 'UNKNOWN_COMMAND'}
    allowed = spec['flags']
    positionals = []
    index = 1
    while index < len(argv):
        token = argv[index]
        if not isinstance(token, str) or '\x00' in token:
            return {'status': 'DENY', 'reason': 'INVALID_ARGUMENT'}
        if token.startswith('-'):
            if '=' in token: # Must not implicitly support argument assignment forms without audit.
                return {'status': 'DENY', 'reason': 'UNDECLARED_FLAG_FORM'}
            nargs = allowed.get(token)
            if nargs is None:
                return {'status': 'DENY', 'reason': 'UNKNOWN_FLAG'}
            if index + nargs >= len(argv):
                return {'status': 'DENY', 'reason': 'FLAG_VALUE_MISSING'}
            if nargs:
                for v in argv[index+1:index+1+nargs]:
                    if not isinstance(v, str) or not v or v.startswith('-') or len(v)>4096 or '\x00' in v:
                        return {'status': 'DENY', 'reason': 'INVALID_FLAG_VALUE'}
            index += nargs + 1
        else:
            positionals.append(token)
            index += 1
    if len(positionals) != len(spec['positional']):
        return {'status': 'DENY', 'reason': 'ARGUMENT_COUNT'}
    for role, value in zip(spec['positional'], positionals):
        if role == 'mode':
            if command != 'serve' or value != 'restic' or '--stdio' not in argv:
                return {'status': 'DENY', 'reason': 'UNSUPPORTED_STREAM'}
        elif not remote_location(value):
            return {'status': 'DENY', 'reason': 'UNSCOPED_OR_INVALID_PATH'}
    # No calls, no config reads, no remote capability grants in R0.
    return {'status': 'DECLARED_NOT_IMPLEMENTED', 'tier': spec['tier'], 'effect': spec['effect']}


def audit_sources(bkx_root, manifest_path=MANIFEST):
    root = Path(bkx_root)
    manifest = json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    errors = []
    for rel, digest in sorted(manifest['sha256'].items()):
        path = root / rel
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            errors.append(rel)
    return errors


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--audit-bkx', metavar='BKX_ROOT')
    p.add_argument('--inspect-argv-json', help='JSON array of CLI args (classification only)')
    args = p.parse_args(argv)
    if bool(args.audit_bkx) == bool(args.inspect_argv_json):
        p.error('provide exactly one of --audit-bkx or --inspect-argv-json')
    load_contract()
    if args.audit_bkx:
        errors = audit_sources(args.audit_bkx)
        print(json.dumps({'status': 'SOURCE_MATCH' if not errors else 'SOURCE_MISMATCH', 'mismatches': errors, 'runtime_invocation_enabled': False},sort_keys=True))
        return 0 if not errors else 2
    try:
        request = json.loads(args.inspect_argv_json)
        if not isinstance(request,list) or not all(isinstance(x,str) for x in request) or len(request)>64:
            raise ValueError('invalid argv')
        result = inspect(request)
    except (ValueError, TypeError, json.JSONDecodeError):
        result = {'status':'DENY', 'reason':'INVALID_JSON_ARGV'}
    print(json.dumps(result,sort_keys=True))
    return 0 if result['status'] == 'DECLARED_NOT_IMPLEMENTED' else 2

if __name__ == '__main__':
    sys.exit(main())
