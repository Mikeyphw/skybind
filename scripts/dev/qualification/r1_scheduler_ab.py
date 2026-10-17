#!/usr/bin/env python3
"""B1-QW2: source-bound, opt-in Termux Devtool R1 scheduler A/B qualification.

This is a witness around Devtool invoke, not a replacement scheduler or test runner.
No Android builds, device changes, release claims, or automatic retries occur.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import tomllib

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / 'build' / 'evidence' / 'r1-scheduler-ab'
GO_EVIDENCE = ROOT / 'build' / 'evidence' / 'go-regression-isolated'
GO_JOBS = {
    'skybind_api_contracts.r1-policy',
    'skybind_api_contracts.r1-transport',
    'skybind_api_contracts.r1-identity',
    'skybind_go.isolated-regression',
}
ALL_JOBS = GO_JOBS | {
    'skybind_bkx_compat.offline',
    'skybind_chrootctl_compat.offline',
    'skybind_api_contracts.r1b-contract',
    'skybind_android_app.build-policy',
}
SCHEMA = 'skybind-r1-scheduler-ab-v1'


class GateError(Exception):
    pass


def require(ok, reason):
    if not ok:
        raise GateError(reason)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as inp:
        for chunk in iter(lambda: inp.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def load_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def utc():
    return datetime.now(timezone.utc).isoformat()


def git(*args):
    p = subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True, text=True, timeout=20)
    require(p.returncode == 0, f'git {args[0]} failed: {p.stderr[:300]}')
    return p.stdout.strip()


def identity():
    require((ROOT / '.devtool.toml').is_file(), 'Devtool config absent')
    require(not git('status', '--porcelain', '--untracked-files=all'), 'working tree is not clean')
    source = git('rev-parse', 'HEAD')
    config = tomllib.loads((ROOT / '.devtool.toml').read_text(encoding='utf-8'))
    sched = config['workspace']['scheduler']
    require(sched['parallel'] is False and sched['max_parallel_nodes'] == 3,
            'unexpected default scheduler policy')
    jobs = config['targets']['skybind_api_contracts']['jobs']
    for name in ('r1-policy', 'r1-transport', 'r1-identity'):
        require(jobs[name]['metadata']['global_reservations'] == ['skybind-go-build-cache'],
                f'{name} missing shared Go reservation')
    gojob = config['targets']['skybind_go']['jobs']['isolated-regression']
    require(gojob['metadata']['read_only'] is False, 'Go evidence producer misclassified read-only')
    require(gojob['metadata']['global_reservations'] == ['skybind-go-build-cache'],
            'Go evidence producer missing reservation')
    require('build/evidence/go-regression-isolated/**' in gojob['outputs'],
            'Go evidence path missing')
    return {'commit': source, 'config_sha256': digest(ROOT / '.devtool.toml')}


def command(mode):
    base = ['devtool', '-r', str(ROOT), '--no-hud', '--no-clipboard']
    args = ['--workflow-parallel', '--workflow-max-workers', '3'] if mode == 'candidate' else ['--no-workflow-parallel']
    return base, args


def plan(mode):
    base, opts = command(mode)
    argv = [*base, 'plan', 'r1-full-regression', '--target', 'skybind_release', *opts, '--json']
    proc = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=120)
    require(proc.returncode == 0, f'Devtool planner failed: {proc.stderr[:500]}')
    envelope = json.loads(proc.stdout)
    require(envelope.get('ok') is True and envelope.get('exit_code') == 0,
            'Devtool planner did not return success')
    data = envelope.get('data') or {}
    require(data.get('action') == 'r1-full-regression' and data.get('targets') == ['skybind_release'],
            'planner resolved unexpected workflow or target')
    schedule = data.get('schedule') or {}
    require(schedule.get('parallel_effective') is (mode == 'candidate'),
            'planner concurrency differs from requested mode')
    if mode == 'candidate':
        require(schedule.get('max_parallel_nodes') == 3, 'candidate worker bound not 3')
    nodes = schedule.get('nodes') or []
    mapping = {n['job_key']: n for n in nodes}
    require(len(nodes) == len(ALL_JOBS) and set(mapping) == ALL_JOBS,
            'planner job set drift: R1 gate missing or extra')
    for name in GO_JOBS:
        require(mapping[name].get('global_reservations') == ['skybind-go-build-cache'],
                f'{name}: unsafe Go reservation')
    writer = mapping['skybind_go.isolated-regression']
    require(writer.get('read_only') is False and writer.get('writes_known') is True,
            'Go evidence writer scope is unsafe')
    require('build/evidence/go-regression-isolated' in writer.get('writes', []),
            'Go evidence output scope lost')
    waves = schedule.get('waves') or []
    require(waves, 'planner produced no scheduling waves')
    keys_to_name = {n['key']: n['job_key'] for n in nodes}
    flattened = []
    for wave in waves:
        active = [keys_to_name[k] for k in wave['nodes']]
        require(len(set(active) & GO_JOBS) <= 1, 'planner overlaps Go build-cache consumers')
        flattened.extend(active)
    require(len(flattened) == len(ALL_JOBS) and set(flattened) == ALL_JOBS,
            'planner waves do not cover exactly all R1 jobs')
    return {'waves': len(waves), 'max_concurrent_go_jobs': 1,
            'plan_sha256': hashlib.sha256(proc.stdout.encode()).hexdigest(),
            'plan': envelope, 'argv': argv}


def check_go_receipt(path, expected_commit):
    require(path.is_file() and not path.is_symlink(), 'Go summary missing or symlinked')
    obj = load_json(path)
    require(obj.get('schema') == 'skybind-go-isolated-regression-v1', 'unexpected Go summary schema')
    require(obj.get('source_commit') == expected_commit, 'Go source commit does not match workflow')
    require(obj.get('complete') is True and obj.get('qualified') is True and
            obj.get('selection_full') is True and obj.get('source_unchanged') is True,
            'Go regression incomplete, diagnostic, or unqualified')
    entries = obj.get('results') or []
    count = obj.get('discovered_packages')
    require(isinstance(count, int) and count > 0 and len(entries) == count and
            obj.get('selected_packages') == count, 'Go package coverage incomplete')
    seen = set()
    for entry in entries:
        pkg = entry.get('package')
        require(isinstance(pkg, str) and pkg.startswith('skybind/') and pkg not in seen,
                'Go package missing or duplicated')
        seen.add(pkg)
        require(entry.get('valid') is True and entry.get('waitdelay') is False and
                entry.get('timed_out') is False and entry.get('exit_code') == 0,
                f'Go test failure or WaitDelay: {pkg}')
        log = entry.get('log')
        require(isinstance(log, str) and re.fullmatch(r'[A-Za-z0-9_.-]+\.jsonl', log),
                'unsafe Go log name')
        logfile = path.parent / log
        require(logfile.is_file() and not logfile.is_symlink() and
                digest(logfile) == entry.get('log_sha256'), f'Go log hash mismatch: {pkg}')
    require(isinstance(obj.get('source_sha256'), str) and len(obj['source_sha256']) == 64,
            'Go source digest missing')
    return {'source_sha256': obj['source_sha256'], 'package_count': count,
            'packages': sorted(seen), 'summary_sha256': digest(path),
            'path': path.relative_to(ROOT).as_posix()}


def go_catalog():
    if not GO_EVIDENCE.is_dir():
        return set()
    return {p.parent.name for p in GO_EVIDENCE.glob('*/summary.json') if p.is_file()}


def run_stage(mode, campaign, max_seconds):
    ident = identity()
    base_dir = EVIDENCE / campaign
    stage_dir = base_dir / mode
    if mode == 'candidate':
        baseline = read_stage(base_dir / 'baseline', 'baseline')
        require(baseline['source'] == ident, 'baseline source differs from candidate')
    require(not stage_dir.exists(), 'stage already exists; no automatic rerun or overwrite')
    checked_plan = plan(mode)  # A dry-run first, always.
    stage_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    before = go_catalog()
    machine = stage_dir / 'devtool-machine.json'
    stdout = stage_dir / 'devtool-output.log'
    base, opts = command(mode)
    argv = [*base, '--machine-file', str(machine), 'invoke', 'r1-full-regression',
            '--target', 'skybind_release', *opts]
    started = time.monotonic()
    started_iso = utc()
    rc = 124
    error = None
    try:
        with stdout.open('wb') as log:
            proc = subprocess.Popen(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                rc = proc.wait(timeout=max_seconds)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=12)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=12)
                error = 'Devtool timed out; child run must be investigated before retry'
    except OSError as exc:
        error = f'Unable to start Devtool: {exc}'
    elapsed = round(time.monotonic() - started, 3)
    receipt = {'schema': SCHEMA, 'stage': mode, 'campaign': campaign,
               'status': 'FAILED_OR_INCOMPLETE', 'source': ident,
               'started_at': started_iso, 'duration_seconds': elapsed, 'exit_code': rc,
               'devtool_argv': argv, 'plan_sha256': checked_plan['plan_sha256'],
               'plan_waves': checked_plan['waves'], 'stdout_sha256': digest(stdout) if stdout.exists() else None,
               'machine_sha256': digest(machine) if machine.exists() else None,
               'error': error}
    try:
        require(rc == 0 and error is None, error or f'Devtool failed exit={rc}')
        require(machine.is_file(), 'Devtool machine envelope missing')
        env = load_json(machine)
        require(env.get('ok') is True and env.get('exit_code') == 0 and env.get('command') == 'invoke',
                'Devtool machine envelope reports incomplete or failed')
        totals = env.get('totals') or {}
        require(totals.get('errors') == 0 and totals.get('failed') == 0,
                'Devtool machine envelope contains failures')
        outputs = env.get('results') or []
        require(len(outputs) == len(ALL_JOBS), 'Devtool returned incomplete workflow node results')
        require(all(r.get('exit_code') == 0 and r.get('status') == 'ok' for r in outputs),
                'Devtool workflow contains failed or skipped nodes')
        after = go_catalog()
        created = after - before
        require(len(created) == 1, f'expected exactly one new full Go receipt; got {len(created)}')
        go = check_go_receipt(GO_EVIDENCE / next(iter(created)) / 'summary.json', ident['commit'])
        require(identity() == ident, 'source or working tree changed while executing')
        receipt['go'] = go
        receipt['status'] = 'PASS_SOURCE_R1_ONLY'
    except (GateError, ValueError, OSError, KeyError, TypeError) as exc:
        receipt['error'] = str(exc)
    (stage_dir / 'receipt.json').write_text(json.dumps(receipt, sort_keys=True, indent=2) + '\n')
    print(json.dumps({'stage': mode, 'status': receipt['status'], 'report': str(stage_dir/'receipt.json'),
                      'duration_seconds': elapsed, 'error': receipt['error']}, sort_keys=True))
    return 0 if receipt['status'] == 'PASS_SOURCE_R1_ONLY' else 1


def read_stage(stage_dir, mode):
    path = stage_dir / 'receipt.json'
    require(path.is_file() and not path.is_symlink(), f'{mode} stage receipt missing')
    info = load_json(path)
    require(info.get('schema') == SCHEMA and info.get('stage') == mode and
            info.get('status') == 'PASS_SOURCE_R1_ONLY', f'{mode} stage is not passed')
    for name, sha in (('devtool-output.log', info.get('stdout_sha256')),
                      ('devtool-machine.json', info.get('machine_sha256'))):
        p = stage_dir / name
        require(p.is_file() and not p.is_symlink() and digest(p) == sha,
                f'{mode}: {name} missing or tampered')
    machine = load_json(stage_dir / 'devtool-machine.json')
    require(machine.get('ok') is True and machine.get('exit_code') == 0,
            f'{mode}: machine did not pass')
    go = info.get('go') or {}
    path = ROOT / str(go.get('path', ''))
    require(path.is_relative_to(GO_EVIDENCE) and path.name == 'summary.json',
            f'{mode}: Go evidence path escaped expected root')
    verified = check_go_receipt(path, info['source']['commit'])
    require(go == verified, f'{mode}: Go receipt or package logs have changed')
    return info


def compare(campaign):
    base = EVIDENCE / campaign
    first, second = read_stage(base / 'baseline', 'baseline'), read_stage(base / 'candidate', 'candidate')
    require(first['source'] == second['source'] == identity(), 'different source between A/B runs')
    a, b = first['go'], second['go']
    require(a['source_sha256'] == b['source_sha256'] and a['packages'] == b['packages'] and
            a['package_count'] == b['package_count'], 'Go coverage/digest parity failed')
    require(second['plan_waves'] <= first['plan_waves'], 'candidate scheduling regressed')
    baseline = first['duration_seconds']; candidate = second['duration_seconds']
    report = {'schema': SCHEMA, 'campaign': campaign, 'status': 'PASS_R1_SCHEDULER_AB_ONLY',
              'source': first['source'], 'go_source_sha256': a['source_sha256'],
              'go_package_count': a['package_count'], 'baseline_seconds': baseline,
              'candidate_seconds': candidate, 'delta_seconds': round(candidate - baseline, 3),
              'candidate_speedup_ratio': round(baseline / candidate, 3) if candidate else None,
              'baseline_waves': first['plan_waves'], 'candidate_waves': second['plan_waves'],
              'notes': 'Measured once; performance variance not statistically resolved. No APK, Android, cross-UID, or release qualification.'}
    output = base / 'comparison.json'
    require(not output.exists(), 'comparison already written; no overwrite')
    output.write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'baseline_seconds': baseline,
                      'candidate_seconds': candidate, 'report': str(output)}, sort_keys=True))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('plan', 'baseline', 'candidate', 'compare'))
    parser.add_argument('--campaign', help='Stable 3–64-character lowercase id for one A/B experiment')
    parser.add_argument('--max-seconds', type=int, default=10800, help='Stage time limit (600–21600 seconds)')
    args = parser.parse_args()
    if args.action != 'plan' and not args.campaign:
        parser.error('--campaign required for baseline/candidate/compare')
    if args.campaign and not re.fullmatch(r'[a-z0-9][a-z0-9-]{2,63}', args.campaign):
        parser.error('campaign must match [a-z0-9][a-z0-9-]{2,63}')
    if not 600 <= args.max_seconds <= 21600:
        parser.error('--max-seconds must be 600..21600')
    try:
        if args.action == 'plan':
            source = identity()
            a, b = plan('baseline'), plan('candidate')
            print(json.dumps({'status': 'PASS_PLAN_ONLY', 'source': source,
                              'baseline_waves': a['waves'], 'candidate_waves': b['waves'],
                              'max_go_parallel': b['max_concurrent_go_jobs']}, sort_keys=True))
            return 0
        if args.action == 'compare':
            return compare(args.campaign)
        return run_stage(args.action, args.campaign, args.max_seconds)
    except (GateError, ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        print(f'BLOCKED: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
