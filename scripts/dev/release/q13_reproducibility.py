#!/usr/bin/env python3
"""SB-Q13: fail-closed, local cross-provider candidate inventory and gate triage.

A/B lane ZIP equality is only a raw observation. It DOES NOT authenticate the
builders, their isolation, author/custody, or independently signed gate receipts.
This script never builds, signs, installs, patches or promotes a release gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts/dev/release'))
sys.path.insert(0, str(ROOT / 'scripts/dev/integration'))
sys.path.insert(0, str(ROOT / 'scripts/dev/gates'))
sys.path.insert(0, str(ROOT / 'scripts/dev/seal'))
import q12_provenance as q12
import q05_candidate as q05
import sb_g01
import sb_g02
import sb_cg1
import sb_cfs1

PROVIDERS = ('newfuture', 'bclone')
H64 = re.compile(r'[0-9a-f]{64}\Z')
SHARED = ('system/bin/skybind', 'system/bin/rclone', 'system/bin/skybind-rclone', 'system/vendor/bin/fusermount3')
MAX_RECEIPT = 1024 * 1024


def sha(path: Path) -> str:
    return q12.hash_file(path)


def local_candidates(root: Path) -> tuple[Path | None, str]:
    base = root / 'dist/local-candidates'
    if not base.is_dir() or base.is_symlink():
        return None, 'NO_LOCAL_CANDIDATES'
    dirs = sorted(p for p in base.glob('candidate-*') if p.is_dir() and not p.is_symlink() and (p / 'candidate-evidence.json').exists())
    if len(dirs) == 1:
        return dirs[0], 'AUTO_SINGLE_LANE'
    if not dirs:
        return None, 'NO_LOCAL_CANDIDATES'
    return None, 'AMBIGUOUS_CANDIDATES_EXPLICIT_LANE_REQUIRED'


def safe_lane(path: Path) -> Path:
    if path.is_symlink() or not path.is_dir():
        raise ValueError('lane must be a real directory (not a symlink)')
    return path.resolve(strict=True)


def inspect_lane(path: Path, root: Path) -> dict:
    """Inspect only exact receipt-named ZIPs using the authoritative Q05 verifier."""
    lane = safe_lane(path)
    receipt_path = lane / 'candidate-evidence.json'
    receipt = q12.single_json(receipt_path)
    if (receipt.get('build_kind') != 'LOCAL_DEVELOPMENT_UNQUALIFIED' or
        receipt.get('final_seal') != 'NOT_ISSUED' or
        receipt.get('independent_attestation') is not False):
        raise ValueError('lane evidence claims unsupported qualification')
    item_map = receipt.get('candidates')
    if not isinstance(item_map, dict) or not set(item_map).issubset(PROVIDERS) or not item_map:
        raise ValueError('lane has invalid provider inventory')
    result = {'status': 'VALID_UNQUALIFIED_LANE', 'lane': str(lane), 'providers': {},
              'build_source': receipt.get('q12_source_build', None),
              'receipt_sha256': sha(receipt_path), 'independent_build': False}
    # Every selected candidate must come from a bounded, canonical, regular ZIP.
    for provider in PROVIDERS:
        if provider not in item_map:
            result['providers'][provider] = {'status': 'MISSING'}
            continue
        desc = item_map[provider]
        if not isinstance(desc, dict):
            raise ValueError('invalid provider receipt')
        name = desc.get('file')
        if (not isinstance(name, str) or not re.fullmatch(r'skybind-(?:newfuture|bclone)-CANDIDATE-UNQUALIFIED\.zip', name)
            or name != f'skybind-{provider}-CANDIDATE-UNQUALIFIED.zip'):
            raise ValueError('noncanonical candidate filename')
        candidate = lane / name
        inspected = q12.inspect_candidate(candidate)
        if (inspected['status'] != 'VALID_UNQUALIFIED_CANDIDATE' or inspected['provider'] != provider or
            not H64.fullmatch(str(desc.get('sha256', ''))) or desc['sha256'] != inspected['sha256']):
            raise ValueError(provider + ': candidate verifier/receipt mismatch: ' + str(inspected.get('reason', ''))[:100])
        result['providers'][provider] = {'status': inspected['status'], 'file': name,
                                         'sha256': inspected['sha256'], 'members': inspected['members']}
    # A missing provider is a real coverage gap, not an excuse to call this 'both providers'.
    if any(item['status'] == 'MISSING' for item in result['providers'].values()):
        result['status'] = 'PARTIAL_PROVIDER_COVERAGE'
    identity = receipt.get('q12_source_build')
    if not isinstance(identity, dict) or identity.get('schema_version') != 1:
        result['source_receipt'] = 'NOT_RECORDED'
    else:
        expected = {p: v['sha256'] for p, v in result['providers'].items() if v['status'] != 'MISSING'}
        if (identity.get('git_clean') is not True or identity.get('candidate_sha256') != expected or
            not re.fullmatch(r'[a-f0-9]{40,64}', str(identity.get('commit', ''))) or
            not re.fullmatch(r'[a-f0-9]{40,64}', str(identity.get('tree', '')))):
            raise ValueError('build-time source receipt inconsistent with candidate inventory')
        result['source_receipt'] = 'LOCAL_SELF_REPORTED_ONLY'
    return result


def same_provider(left: dict, right: dict) -> dict:
    results = {}
    for provider in PROVIDERS:
        a = left['providers'][provider]
        b = right['providers'][provider]
        if a['status'] != 'VALID_UNQUALIFIED_CANDIDATE' or b['status'] != 'VALID_UNQUALIFIED_CANDIDATE':
            results[provider] = {'status': 'MISSING_LANE_PROVIDER'}
        else:
            same_bytes = a['sha256'] == b['sha256']
            same_manifest = a['members'] == b['members']
            results[provider] = {'status': 'BYTE_IDENTICAL_UNATTESTED' if same_bytes and same_manifest else 'DIFFERENT_BYTES',
                                 'byte_identical': same_bytes, 'installed_member_hashes_identical': same_manifest,
                                 'lane_a_sha256': a['sha256'], 'lane_b_sha256': b['sha256']}
    return results


def cross_provider(lane: dict) -> dict:
    a, b = (lane['providers'][p] for p in PROVIDERS)
    if a['status'] != 'VALID_UNQUALIFIED_CANDIDATE' or b['status'] != 'VALID_UNQUALIFIED_CANDIDATE':
        return {'status': 'BOTH_PROVIDERS_REQUIRED'}
    matches = {item: a['members'][item] == b['members'][item] for item in SHARED}
    # Runtime provider 'rclone' binary and runtime provenance are EXPECTED to differ.
    return {'status': 'SHARED_PAYLOAD_MATCH_UNATTESTED' if all(matches.values()) else 'SHARED_PAYLOAD_MISMATCH',
            'shared_payload': matches,
            'provider_runtime_distinct': a['members']['system/bin/skybind-rclone-engine'] != b['members']['system/bin/skybind-rclone-engine'],
            'runtime_binaries_expected_to_differ': True}


def gate_diagnostics(root: Path) -> tuple[dict, dict]:
    # Consult the actual original evaluators. No synthetic receipts or gate states.
    g1 = sb_g01.evaluate(root=root)
    g2 = sb_g02.evaluate(root=root, g01_result=g1)
    later = sb_cg1.evaluate_all(root=root)
    final = sb_cfs1.evaluate(root=root)
    results = {}
    for gate, item in [('SB-G01', g1), ('SB-G02', g2)]:
        results[gate] = {'status': item.get('status', 'BLOCKED'), 'reasons': item.get('reasons', [])}
    for gate in sb_cg1.GATES:
        item = later['gates'][gate]
        results[gate] = {'status': item.get('status', 'BLOCKED'), 'reasons': item.get('reasons', []),
                         'dependencies': list(sb_cg1.REQUIRES[gate])}
    return results, {'status': final.get('status', 'BLOCKED'), 'seal': final.get('final_seal', 'NOT_ISSUED'),
                     'reasons': final.get('reasons', [])}


def inspect_q04(root: Path, supplied: Path | None) -> dict:
    path = supplied if supplied is not None else root / 'build/local-q04-evidence'
    if not path.exists():
        return {'status': 'Q04_EVIDENCE_NOT_PROVIDED'}
    try:
        inv = q05.evidence_inventory(path)
        return {'status': 'PINNED_Q04_RAW_INPUTS_VERIFIED_UNATTESTED',
                'selection': inv.get('selection', {}), 'independent_attestation': False}
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        return {'status': 'Q04_INVALID', 'reason': type(exc).__name__ + ': ' + str(exc)[:160]}


def evaluate(root: Path, *, lane_a: Path | None = None, lane_b: Path | None = None,
             q04_path: Path | None = None, source_only: bool = False) -> dict:
    selected, discovery = local_candidates(root) if lane_a is None else (lane_a, 'EXPLICIT')
    a = None
    b = None
    issues = []
    if lane_b is not None and lane_a is None:
        issues.append('SECOND_LANE_REQUIRES_EXPLICIT_FIRST_LANE')
    if selected is not None:
        try:
            a = inspect_lane(selected, root)
        except (OSError, KeyError, ValueError, TypeError) as exc:
            issues.append('LANE_A_INVALID_' + type(exc).__name__ + ': ' + str(exc)[:150])
    else:
        issues.append(discovery)
    if lane_b is not None and lane_a is not None:
        try:
            if safe_lane(lane_b) == safe_lane(lane_a):
                raise ValueError('lane A and B must be distinct directories')
            b = inspect_lane(lane_b, root)
        except (OSError, KeyError, ValueError, TypeError) as exc:
            issues.append('LANE_B_INVALID_' + type(exc).__name__ + ': ' + str(exc)[:150])
    lanes = [i for i in (a, b) if i is not None]
    pair = same_provider(a, b) if a is not None and b is not None else {p: {'status': 'SECOND_BUILD_LANE_NOT_PROVIDED'} for p in PROVIDERS}
    parity = [cross_provider(item) for item in lanes]
    try:
        gates, final = gate_diagnostics(root)
    except (OSError, ValueError, KeyError, ImportError, TypeError) as exc:
        issues.append('RELEASE_EVALUATOR_UNAVAILABLE_' + type(exc).__name__)
        gates = {f'SB-G{i:02}': {'status': 'BLOCKED', 'reasons': ['EVALUATOR_UNAVAILABLE']} for i in range(1, 9)}
        final = {'status': 'BLOCKED', 'seal': 'NOT_ISSUED', 'reasons': ['EVALUATOR_UNAVAILABLE']}
    q04 = inspect_q04(root, q04_path) if not source_only else {'status': 'NOT_CHECKED_SOURCE_ONLY'}
    report = {'schema_version': 1, 'campaign': 'SB-Q13', 'status': 'LOCAL_COMPARISON_ONLY_NOT_RELEASE_QUALIFIED',
              'final_seal': 'NOT_ISSUED', 'independent_attestation': False,
              'source': q12.source_identity(root), 'selection': discovery, 'issues': issues,
              'provider_names': list(PROVIDERS), 'lanes': lanes, 'same_provider_repeat_build_comparison': pair,
              'cross_provider_shared_payload': parity, 'q04_pinned_input_inventory': q04,
              'gate_blockers': gates, 'external_final_seal_evaluator': final,
              'remaining': ['TWO_INDEPENDENT_VERIFIABLE_BUILD_LANES_PER_PROVIDER',
                            'EXTERNALLY_AUTHENTICATED_SOURCE_BUILD_DEVICE_CHAIN',
                            'SIGNED_G01_G08_GATE_RECEIPTS', 'PHYSICAL_MANAGER_NEGATIVE_SECURITY_MATRIX',
                            'ORIGINAL_WEBVIEW_BROWSER_ACCESSIBILITY_MATRIX', 'EXTERNAL_FINAL_SEAL'],
              'limitations': ['Candidate byte equality does not establish independent builders or custody',
                              'The provider binary is intentionally different across newfuture and bclone',
                              'Local checks and Q04 inputs never promote G01-G08 or produce signed evidence']}
    return report


def markdown(data: dict) -> str:
    lines = ['# Skybind SB-Q13 — Provider Reproducibility & Gate Diagnostics', '',
             '**Release: NOT_ISSUED** · Local checks are not independent attestation.', '',
             '## Build lanes', '', '| Provider | A↔B comparison |', '|---|---|']
    for p, item in data['same_provider_repeat_build_comparison'].items():
        lines.append(f"| {p} | {item['status']} |")
    lines += ['', '## Cross-provider shared payloads', '']
    for i, entry in enumerate(data['cross_provider_shared_payload'], 1):
        lines.append(f"- Lane {i}: {entry['status']}")
    lines += ['', '## Independent gate blockers', '', '| Gate | Actual status | Reasons |', '|---|---|---|']
    for gate, item in sorted(data['gate_blockers'].items()):
        reasons = ', '.join(str(s) for s in item.get('reasons', [])) or 'None'
        lines.append(f"| {gate} | {item['status']} | {reasons.replace('|', '/')} |")
    lines += ['', '## Issues', '']
    lines.extend('- ' + str(issue) for issue in data['issues'])
    if not data['issues']:
        lines.append('- No input integrity errors')
    lines += ['', '### Assurance boundary', '',
              'This tool never certifies independence, signs a gate receipt or issues a final release seal.', '']
    return '\n'.join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repository', type=Path, default=ROOT)
    p.add_argument('--lane-a', type=Path, help='First candidate-* directory (containing candidate-evidence.json)')
    p.add_argument('--lane-b', type=Path, help='Second independently produced candidate-* directory')
    p.add_argument('--q04-evidence-root', type=Path, help='Verified upstream evidence directory')
    p.add_argument('--output-dir', type=Path, default=Path('/storage/emulated/0/Download'))
    p.add_argument('--source-only', action='store_true', help='Do not inspect Q04 evidence')
    args = p.parse_args(argv)
    try:
        result = evaluate(args.repository.resolve(), lane_a=args.lane_a, lane_b=args.lane_b,
                          q04_path=args.q04_evidence_root, source_only=args.source_only)
        q12.safe_output(args.output_dir, 'skybind-q13-summary.json',
                        (json.dumps(result, sort_keys=True, indent=2) + '\n').encode())
        q12.safe_output(args.output_dir, 'skybind-q13-summary.md', markdown(result).encode())
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print('SB-Q13 blocked: ' + type(exc).__name__ + ': ' + str(exc)[:150], file=sys.stderr)
        return 3
    print(json.dumps({'status': result['status'], 'issues': result['issues'],
                      'lanes': len(result['lanes']), 'final_seal': 'NOT_ISSUED',
                      'output_dir': str(args.output_dir)}, sort_keys=True))
    return 3 if any('INVALID' in x or 'REQUIRES' in x for x in result['issues']) else 0


if __name__ == '__main__':
    raise SystemExit(main())
