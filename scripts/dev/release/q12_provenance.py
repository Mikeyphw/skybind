#!/usr/bin/env python3
"""SB-Q12 local provenance inventory (not an attestation or release signer).

Candidate validation delegates to the existing Q05 release verifier.  Installed
bytes are read from one fixed module location; no mounts or app data are touched.
Hash equality is an observation, *not* a source/reproducibility proof.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts/dev/release'))
import skybind_release as release
import q11_reconcile as q11

H64 = re.compile(r'[0-9a-f]{64}\Z')
FILES = ('system/bin/skybind', 'system/bin/rclone', 'system/vendor/bin/fusermount3', 'runtime.provenance.json')
INSTALLED = '/data/adb/modules/skybind'
MAX_ARCHIVE = 600 * 1024 * 1024
MAX_REPORT = 1024 * 1024


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as handle:
        while block := handle.read(1024 * 1024):
            h.update(block)
    return h.hexdigest()


def single_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_REPORT:
        raise ValueError('missing/linked/oversized JSON input')
    obj = json.loads(path.read_bytes())
    if not isinstance(obj, dict):
        raise ValueError('expected JSON object')
    return obj


def candidates(root: Path, explicit: Path | None) -> tuple[Path | None, str]:
    if explicit is not None:
        return explicit, 'EXPLICIT'
    base = root / 'dist/local-candidates'
    found = sorted(base.glob('candidate-*/skybind-*-CANDIDATE-UNQUALIFIED.zip')) if base.is_dir() and not base.is_symlink() else []
    if not found:
        return None, 'NO_CANDIDATE'
    if len(found) > 1:
        return None, 'AMBIGUOUS_CANDIDATES_EXPLICIT_SELECTION_REQUIRED'
    return found[0], 'AUTO_SINGLE'


def inspect_candidate(path: Path) -> dict:
    result = {'status': 'INVALID', 'file': path.name, 'sha256': None, 'provider': None, 'members': {}}
    try:
        if path.is_symlink() or not path.is_file() or not (0 < path.stat().st_size <= MAX_ARCHIVE):
            raise ValueError('missing, linked or oversized candidate')
        # Authoritative Q05 candidate verifier checks checksums, canonical ZIP,
        # runtime provenance, all required contents, and arm64 executables.
        proof = release.verify_release(path)
        if proof.get('qualification') != 'CANDIDATE_ONLY_NOT_SEALED' or proof.get('runtime_provider') not in ('newfuture', 'bclone'):
            raise ValueError('unexpected candidate qualification/provider')
        with zipfile.ZipFile(path) as arc:
            names = set(arc.namelist())
            if not set(FILES).issubset(names):
                raise ValueError('candidate missing required installed payload')
            members = {name: proof['files'][name]['sha256'] if name in proof['files'] else None for name in FILES}
            # runtime.provenance.json appears in manifest inventory too.
            if any(not isinstance(value, str) or not H64.fullmatch(value) for value in members.values()):
                raise ValueError('invalid member manifest hashes')
        result.update(status='VALID_UNQUALIFIED_CANDIDATE', sha256=hash_file(path), provider=proof['runtime_provider'], members=members)
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, release.Reject) as exc:
        result['reason'] = type(exc).__name__ + ': ' + str(exc)[:150]
    return result


def _root_hash(member: str) -> str | None:
    # Fully fixed command; never allow arbitrary paths or interpolated shell text.
    absolute = INSTALLED + '/' + member
    cmd = ['/system/bin/sha256sum', absolute]
    try:
        r = subprocess.run(['su', '-c', ' '.join(cmd)], capture_output=True, text=True, timeout=15, check=False)
        if r.returncode:
            return None
        line = r.stdout.strip().splitlines()
        if len(line) != 1:
            return None
        match = re.fullmatch(r'([0-9a-f]{64})\s+\*?' + re.escape(absolute), line[0])
        return match.group(1) if match else None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def inspect_installed(*, fixture: Path | None = None) -> dict:
    observed = {}
    for member in FILES:
        if fixture is None:
            observed[member] = _root_hash(member)
        else:
            item = fixture / member
            if not item.is_file() or item.is_symlink():
                observed[member] = None
            else:
                observed[member] = hash_file(item)
    return {'status': 'ROOT_HASHES_OBSERVED' if all(observed.values()) else 'INCOMPLETE_OR_NO_ROOT_ACCESS',
            'members': observed, 'module': 'skybind'}


def inspect_build_receipt(candidate: Path | None, checked: dict, root: Path, source: dict) -> dict:
    result = {'status': 'NO_BUILD_TIME_SOURCE_RECEIPT', 'source_to_candidate': 'NOT_PROVEN'}
    if candidate is None or checked.get('status') != 'VALID_UNQUALIFIED_CANDIDATE':
        return result
    path = candidate.parent / 'candidate-evidence.json'
    if not path.is_file():
        return result
    try:
        obj = single_json(path)
        if obj.get('final_seal') != 'NOT_ISSUED' or obj.get('independent_attestation') is not False or obj.get('build_kind') != 'LOCAL_DEVELOPMENT_UNQUALIFIED':
            raise ValueError('unexpected local build receipt qualification')
        item = obj['candidates'][checked['provider']]
        if item['file'] != candidate.name or item['sha256'] != checked['sha256']:
            raise ValueError('local build receipt candidate mismatch')
        recorded = obj.get('q12_source_build')
        if not isinstance(recorded, dict) or recorded.get('schema_version') != 1:
            return result
        if (recorded.get('git_clean') is not True or recorded.get('candidate_sha256', {}).get(checked['provider']) != checked['sha256'] or
            not isinstance(recorded.get('commit'), str) or not re.fullmatch('[a-f0-9]{40,64}', recorded['commit']) or
            not isinstance(recorded.get('tree'), str) or not re.fullmatch('[a-f0-9]{40,64}', recorded['tree'])):
            raise ValueError('invalid source/build-time receipt binding')
        if recorded['commit'] != source['commit'] or recorded['tree'] != source['tree']:
            return {'status': 'RECORDED_SOURCE_DIFFERS_FROM_CURRENT', 'source_to_candidate': 'NOT_PROVEN',
                    'build_commit': recorded['commit'], 'build_tree': recorded['tree']}
        return {'status': 'MATCHING_LOCAL_BUILD_TIME_RECORD_NOT_INDEPENDENT',
                'source_to_candidate': 'LOCAL_SELF_REPORTED_ONLY', 'build_commit': recorded['commit'], 'build_tree': recorded['tree']}
    except (OSError, KeyError, TypeError, ValueError) as exc:
        return {'status': 'INVALID_BUILD_RECEIPT', 'source_to_candidate': 'NOT_PROVEN', 'reason': str(exc)[:140]}


def get_baseline(evidence: Path, session: str | None) -> dict:
    try:
        if not evidence.is_dir():
            raise ValueError('evidence directory unavailable')
        sid, records, rejected = q11.pick_session(list(evidence.glob('skybind-q09-*.zip')), session)
        if sid is not None and any(sid in row.get('file', '') for row in rejected):
            raise ValueError('selected session contains corrupt files')
        baseline = records.get('baseline', {}).get('report')
        if baseline is None:
            return {'status': 'NO_Q09_BASELINE', 'session': sid, 'binary_sha256': None}
        digest = baseline.get('installed_binary_sha256')
        if not isinstance(digest, str) or not H64.fullmatch(digest):
            raise ValueError('Q09 baseline binary checksum invalid')
        return {'status': 'RAW_BASELINE_CHECKSUM_VERIFIED', 'session': sid, 'binary_sha256': digest}
    except (ValueError, OSError, zipfile.BadZipFile) as exc:
        return {'status': 'INVALID_OR_UNAVAILABLE_Q09_EVIDENCE', 'binary_sha256': None, 'reason': str(exc)[:160]}


def source_identity(root: Path) -> dict:
    return q11.source_identity(root)


def reconcile(root: Path, evidence: Path, candidate: Path | None, *, fixture: Path | None = None, session: str | None = None) -> dict:
    source = source_identity(root)
    chosen, selection = candidates(root, candidate)
    cand = inspect_candidate(chosen) if chosen else {'status': selection, 'file': None, 'sha256': None, 'provider': None, 'members': {}}
    installed = inspect_installed(fixture=fixture)
    baseline = get_baseline(evidence, session)
    hashes_equal = (cand['status'] == 'VALID_UNQUALIFIED_CANDIDATE' and installed['status'] == 'ROOT_HASHES_OBSERVED'
                    and all(cand['members'][member] == installed['members'][member] for member in FILES))
    match_q09 = (hashes_equal and baseline['status'] == 'RAW_BASELINE_CHECKSUM_VERIFIED'
                 and baseline['binary_sha256'] == installed['members']['system/bin/skybind'])
    receipt = inspect_build_receipt(chosen, cand, root, source)
    gates = q11.evaluate_gates(root)
    return {'schema_version': 1, 'campaign': 'SB-Q12', 'status': 'LOCAL_PROVENANCE_INVENTORY_ONLY',
            'final_seal': 'NOT_ISSUED', 'independent_attestation': False,
            'source': source, 'candidate': cand, 'selection': selection,
            'build_receipt': receipt, 'installed_module': installed, 'q09_baseline': baseline,
            'bindings': {'candidate_to_installed': 'LOCAL_HASH_MATCH_NOT_ATTESTED' if hashes_equal else 'NOT_PROVEN',
                         'q09_baseline_to_candidate': 'RAW_HASH_MATCH_NOT_ATTESTED' if match_q09 else 'NOT_PROVEN',
                         'source_to_candidate': receipt['source_to_candidate'],
                         'independent_source_build_device': 'NOT_PROVEN'},
            'independent_gate_evaluation': gates,
            'remaining': ['EXTERNALLY_ATTESTED_SOURCE_BUILD_DEVICE_CHAIN', 'BOTH_PROVIDERS_REPRODUCIBILITY',
                          'G01_G08_SIGNED_GATE_EVIDENCE', 'NEGATIVE_SECURITY_AND_MANAGER_MATRIX',
                          'ORIGINAL_WEBVIEW_BROWSER_ACCESSIBILITY_MATRIX', 'EXTERNAL_FINAL_SEAL'],
            'limitations': ['Checksums alone cannot establish authorship or independent custody',
                            'A local build-time receipt is not independently authenticated',
                            'No release gates are promoted by this tool']}


def summarize(data: dict) -> str:
    lines = ['# Skybind SB-Q12 — Source / Candidate / Device Inventory', '',
             '**Final seal: NOT_ISSUED** · local observations only', '',
             '| Obligation | Status |', '|---|---|',
             '| Candidate archive | '+data['candidate']['status']+' |',
             '| Candidate ↔ installed payload | '+data['bindings']['candidate_to_installed']+' |',
             '| Candidate ↔ Q09 baseline | '+data['bindings']['q09_baseline_to_candidate']+' |',
             '| Source ↔ candidate | '+data['bindings']['source_to_candidate']+' |',
             '| Independent source/build/device | NOT_PROVEN |',
             '| External final seal | NOT_ISSUED |', '', '## Independent release gates', '']
    for gate in [f'SB-G{i:02d}' for i in range(1, 9)]:
        lines.append('- '+gate+': '+data['independent_gate_evaluation'].get('milestone_gates', {}).get(gate, 'UNKNOWN'))
    lines.extend(['', 'No signed gate receipt or release attestation is generated by Q12.', ''])
    return '\n'.join(lines)


def safe_output(output: Path, name: str, raw: bytes) -> Path:
    if output.is_symlink() or not output.is_dir():
        raise ValueError('output directory missing or linked')
    target = output / name
    if target.is_symlink():
        raise ValueError('output target is symlink')
    fd, tmp = tempfile.mkstemp(prefix='.skybind-q12-', dir=output)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return target


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repository', type=Path, default=ROOT)
    p.add_argument('--evidence-dir', type=Path, default=Path('/storage/emulated/0/Download'))
    p.add_argument('--output-dir', type=Path, default=Path('/storage/emulated/0/Download'))
    p.add_argument('--candidate', type=Path, help='Explicit unqualified candidate ZIP; recommended when more than one exists')
    p.add_argument('--session', type=str)
    args = p.parse_args(argv)
    try:
        report = reconcile(args.repository.resolve(), args.evidence_dir, args.candidate, session=args.session)
        out = safe_output(args.output_dir, 'skybind-q12-summary.json', (json.dumps(report, sort_keys=True, indent=2)+'\n').encode())
        safe_output(args.output_dir, 'skybind-q12-summary.md', summarize(report).encode())
    except (OSError, ValueError, KeyError) as exc:
        print('SB-Q12 blocked: '+str(exc), file=sys.stderr)
        return 3
    print(json.dumps({'status': report['status'], 'final_seal': 'NOT_ISSUED', 'summary': str(out),
                      'bindings': report['bindings'], 'candidate_status': report['candidate']['status']}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
