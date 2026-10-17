#!/usr/bin/env python3
"""Skybind B01: independently execute and attest every Go package.

No Android build, no cloud calls, no privileged operation. This is a native
Termux workaround for an intermittently failing multi-package Go invocation;
never recodes a Go failure or WaitDelay as a pass.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
# Do not honor ambient GOFLAGS=-run/-skip/-short/-tags that could silently
# reduce coverage. The standalone Skybind module does not require go.work.
GO_ENV = {**os.environ, "GOFLAGS": "", "GOWORK": "off"}
SCHEMA = "skybind-go-isolated-regression-v1"


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def call(args: list[str], *, timeout=45):
    try:
        p = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=timeout, check=False, env=GO_ENV)
        return p.returncode, p.stdout.decode('utf-8', 'replace').strip(), p.stderr.decode('utf-8', 'replace').strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, "", f"{type(exc).__name__}: {exc}"


def source_digest():
    files = []
    for sub in ('cmd', 'internal'):
        d = ROOT / sub
        if not d.is_dir() or d.is_symlink():
            raise RuntimeError(f"missing/untrusted source directory: {sub}")
        files.extend(p for p in d.rglob('*.go'))
    for name in ('go.mod', 'go.sum', 'go.work'):
        p = ROOT / name
        if p.is_file() or p.is_symlink():
            files.append(p)
    h = hashlib.sha256()
    for p in sorted(files, key=lambda v: str(v.relative_to(ROOT))):
        if p.is_symlink() or not p.is_file():
            raise RuntimeError(f"untrusted source file {p.relative_to(ROOT)}")
        rel = p.relative_to(ROOT).as_posix()
        h.update(len(rel).to_bytes(4, 'big'))
        h.update(rel.encode('utf-8'))
        b = p.read_bytes()
        h.update(len(b).to_bytes(8, 'big'))
        h.update(hashlib.sha256(b).digest())
    if not files:
        raise RuntimeError("empty source inventory")
    return h.hexdigest(), len(files)


def json_objects(raw: str):
    dec = json.JSONDecoder()
    items = []
    offset = 0
    while offset < len(raw):
        while offset < len(raw) and raw[offset].isspace():
            offset += 1
        if offset >= len(raw):
            break
        item, offset = dec.raw_decode(raw, offset)
        if not isinstance(item, dict):
            raise ValueError('non-object Go list response')
        items.append(item)
    return items


def package_catalog():
    rc, stdout, stderr = call(['go', 'list', '-json', './...'], timeout=120)
    if rc or not stdout:
        raise RuntimeError(f"go list failed rc={rc} stderr={stderr[:1000]}")
    raw = json_objects(stdout)
    if not raw:
        raise RuntimeError('go list returned zero packages')
    seen = set()
    packages = []
    for obj in raw:
        pkg = obj.get('ImportPath')
        if not isinstance(pkg, str) or not pkg.startswith('skybind/') or pkg in seen:
            raise RuntimeError('missing, duplicate, or unexpected import path in Go list')
        if obj.get('Error') or obj.get('Incomplete'):
            raise RuntimeError(f'Go list package incomplete: {pkg}')
        seen.add(pkg)
        packages.append({'import_path': pkg, 'has_tests': bool(obj.get('TestGoFiles') or obj.get('XTestGoFiles'))})
    return sorted(packages, key=lambda p: p['import_path'])


def atomic_receipt(path: Path, receipt: dict):
    temp = path.with_name(path.name + '.pending')
    data = (json.dumps(receipt, sort_keys=True, indent=2) + '\n').encode()
    fd = os.open(temp, os.O_CREAT | os.O_WRONLY | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'wb') as w:
        w.write(data)
        w.flush()
        os.fsync(w.fileno())
    temp.replace(path)


def parse_events(path: Path, expected: str, has_tests: bool, rc: int):
    root_terminal = []
    ntest_pass = 0
    ntest_fail = 0
    events = 0
    invalid = 0
    waitdelay = False
    with path.open('rb') as f:
        for line in f:
            if b'WaitDelay expired' in line or b'Test I/O incomplete' in line:
                waitdelay = True
            try:
                evt = json.loads(line)
            except (ValueError, UnicodeError):
                invalid += 1
                continue
            if not isinstance(evt, dict) or evt.get('Package') != expected or evt.get('Action') not in {
                    'start','run','pause','cont','output','pass','fail','skip','bench'}:
                invalid += 1
                continue
            events += 1
            a, test = evt['Action'], evt.get('Test')
            if test is None and a in ('pass', 'fail', 'skip'):
                root_terminal.append(a)
            elif test and a == 'pass':
                ntest_pass += 1
            elif test and a == 'fail':
                ntest_fail += 1
    expected_terminal = 'pass' if has_tests else 'skip'
    valid = rc == 0 and not waitdelay and not invalid and len(root_terminal) == 1 and root_terminal[0] == expected_terminal and ntest_fail == 0
    return {
        'valid': valid, 'events': events, 'invalid_json_events': invalid,
        'terminal_events': root_terminal, 'expected_terminal': expected_terminal,
        'test_pass_events': ntest_pass, 'test_fail_events': ntest_fail,
        'waitdelay': waitdelay,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--timeout-seconds', type=int, default=240, help='Per-package wall timeout (75–900 seconds)')
    ap.add_argument('--only', action='append', help='Run only a named Go import path (diagnostic, never full qualification)')
    args = ap.parse_args()
    if not 75 <= args.timeout_seconds <= 900:
        ap.error('--timeout-seconds must be 75..900')
    if not (ROOT / 'go.mod').is_file():
        ap.error('Skybind go.mod not found relative to script')
    try:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        out = ROOT / 'build' / 'evidence' / 'go-regression-isolated' / stamp
        out.mkdir(parents=True, mode=0o700, exist_ok=False)
        os.chmod(out, 0o700)
        original_digest, nfiles = source_digest()
        packages = package_catalog()
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'BLOCKED preflight: {exc}', file=sys.stderr)
        return 2
    desired = {p['import_path'] for p in packages}
    if args.only:
        if len(set(args.only)) != len(args.only) or not set(args.only) <= desired:
            ap.error('--only must name unique discovered import paths')
        packages_to_run = [p for p in packages if p['import_path'] in set(args.only)]
    else:
        packages_to_run = packages
    sha_rc, sha, _ = call(['git', 'rev-parse', 'HEAD'], timeout=10)
    go_rc, go_version, _ = call(['go','version'])
    receipt = {
        'schema': SCHEMA, 'complete': False, 'qualified': False,
        'milestone_qualified': False, 'captured_at': utcnow(),
        'source_commit': sha if sha_rc == 0 else 'unavailable',
        'source_sha256': original_digest, 'source_file_count': nfiles,
        'go_version': go_version if go_rc == 0 else 'unavailable',
        'go_env_policy': {'GOFLAGS': '', 'GOWORK': 'off'},
        'discovered_packages': len(packages), 'selected_packages': len(packages_to_run),
        'selection_full': not args.only, 'results': [],
        'notes': 'Full Go package regression only; does not qualify cross-UID, Android APK, or device gates.',
    }
    dest = out / 'summary.json'
    atomic_receipt(dest, receipt)
    print(f'Source {original_digest[:12]} | {len(packages_to_run)}/{len(packages)} packages | report {dest}', flush=True)
    all_ok = True
    for index, p in enumerate(packages_to_run, 1):
        pkg = p['import_path']
        name = pkg.replace('/','_') + '.jsonl'
        log = out / name
        argv = ['go','test','-json','-count=1','-p','1',f'-timeout={args.timeout_seconds - 30}s',pkg]
        elapsed = time.monotonic()
        timed_out = False
        print(f'[{index}/{len(packages_to_run)}] {pkg}', flush=True)
        fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os,'O_NOFOLLOW',0), 0o600)
        with os.fdopen(fd,'wb') as f:
            try:
                proc = subprocess.Popen(argv, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT, start_new_session=True, env=GO_ENV)
                try:
                    rc = proc.wait(timeout=args.timeout_seconds)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    os.killpg(proc.pid, signal.SIGKILL)
                    rc = proc.wait()
            except OSError as exc:
                rc = 127
                f.write(f'launch failed: {type(exc).__name__}: {exc}\n'.encode())
        result = parse_events(log, pkg, p['has_tests'], rc)
        result.update({
            'package': pkg, 'exit_code': rc, 'timed_out': timed_out,
            'elapsed_seconds': round(time.monotonic()-elapsed,3),
            'command': argv, 'log': name,
            'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest(),
        })
        result['valid'] = result['valid'] and not timed_out
        receipt['results'].append(result)
        if not result['valid']:
            all_ok = False
        atomic_receipt(dest, receipt)
        print(f'  {"PASS" if result["valid"] else "FAIL"}: rc={rc} {result["elapsed_seconds"]}s tests={result["test_pass_events"]} waitdelay={result["waitdelay"]}', flush=True)
    try:
        ending_digest, count2 = source_digest()
    except (OSError, ValueError, RuntimeError):
        ending_digest, count2 = 'unavailable', -1
    receipt['source_unchanged'] = ending_digest == original_digest and count2 == nfiles
    receipt['complete'] = len(receipt['results']) == len(packages_to_run)
    receipt['qualified'] = bool(all_ok and receipt['complete'] and receipt['source_unchanged'] and receipt['selection_full'])
    receipt['finished_at'] = utcnow()
    atomic_receipt(dest, receipt)
    print(f'Go regression: {"PASS" if receipt["qualified"] else "FAILED_OR_DIAGNOSTIC"}; evidence={dest}', flush=True)
    return 0 if receipt['qualified'] else 1

if __name__ == '__main__':
    sys.exit(main())
