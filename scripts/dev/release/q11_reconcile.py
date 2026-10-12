#!/usr/bin/env python3
"""SB-Q11: reconcile *raw* Q09 device evidence with independent release gates.

Read-only against the source, installed module, and input ZIPs. Not an attester,
release signer or replacement for Devtool gate receipts.
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
import zipfile

ROOT = Path(__file__).resolve().parents[3]
PHASES = ('baseline', 'postboot', 'endurance', 'manual', 'app-probe')
H64 = re.compile(r'[0-9a-f]{64}\Z')
ZIP_NAME = re.compile(r'skybind-q09-[A-Za-z0-9_-]+-(baseline|postboot|endurance|manual|app-probe)-[A-Za-z0-9_-]+\.zip\Z')
MAX_ENTRY = 6 * 1024 * 1024


class EvidenceError(ValueError):
    pass


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def reliable_hash(value: object) -> bool:
    return isinstance(value, str) and H64.fullmatch(value) is not None and len(set(value)) > 4


def load_zip(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 12 * 1024 * 1024:
        raise EvidenceError('unsafe evidence input')
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if len(names) != 3 or set(names) != {'report.json', 'SUMMARY.txt', 'SHA256SUMS'}:
            raise EvidenceError('unexpected ZIP members')
        for item in z.infolist():
            if item.file_size > MAX_ENTRY or (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise EvidenceError('oversized or symlink member')
        raw = {name: z.read(name) for name in names}
    try:
        lines = raw['SHA256SUMS'].decode('ascii').splitlines()
        expected = {}
        for line in lines:
            match = re.fullmatch(r'([a-f0-9]{64})  (report\.json|SUMMARY\.txt)', line)
            if not match or match[2] in expected:
                raise EvidenceError('invalid SHA256SUMS entry')
            expected[match[2]] = match[1]
        if set(expected) != {'report.json', 'SUMMARY.txt'}:
            raise EvidenceError('SHA256SUMS inventory incomplete')
        if any(sha(raw[name]) != expected[name] for name in expected):
            raise EvidenceError('SHA256 mismatch')
        report = json.loads(raw['report.json'])
    except (UnicodeError, ValueError, TypeError) as e:
        raise EvidenceError('invalid report or checksums: ' + str(e)) from e
    if not isinstance(report, dict) or report.get('schema_version') != 1 or report.get('kind') != 'SKYBIND_SB_Q09_RAW' or report.get('qualification') != 'RAW_DEVICE_EVIDENCE_NOT_ATTESTED':
        raise EvidenceError('wrong report schema or unsupported assurance')
    if not isinstance(report.get('device'), dict) or not isinstance(report.get('checks'), list) or not isinstance(report.get('observations'), dict) or not isinstance(report.get('baseline'), dict):
        raise EvidenceError('malformed report fields')
    if not all(isinstance(x, dict) for x in report['checks']):
        raise EvidenceError('invalid check entry')
    session = report.get('session_id')
    if not isinstance(session, str) or not re.fullmatch(r'[0-9TZ-]{16,30}-[0-9a-f]{8}', session):
        raise EvidenceError('invalid session')
    return {'report': report, 'archive_sha256': sha(path.read_bytes()), 'basename': path.name}


def check(report: dict, name: str, status: str = 'PASS') -> bool:
    return any(isinstance(x, dict) and x.get('name') == name and x.get('status') == status for x in report.get('checks', []))


def reconcile_session(records: dict[str, dict]) -> dict:
    base = records.get('baseline', {}).get('report')
    categories = {}
    if base is None:
        return {'status': 'INCOMPLETE', 'checks': {p: 'MISSING' for p in PHASES}, 'problems': ['BASELINE_MISSING']}
    device = base.get('device') or {}
    keys = ('session_id', 'installed_binary_sha256', 'mount_identity_sha256', 'mountpoint_sha256')
    reasons = []
    if any(not reliable_hash(base.get(k)) for k in keys[1:]):
        reasons.append('INVALID_BASELINE_HASH')
    if not reliable_hash(device.get('device_fingerprint_sha256')) or device.get('is_emulator') in ('1', 1, True, 'true'):
        reasons.append('UNTRUSTWORTHY_PHYSICAL_DEVICE_CLAIM')
    if not check(base, 'baseline_mount') or not check(base, 'physical_device_precheck'):
        reasons.append('BASELINE_CHECKS_MISSING')
    for phase, obj in records.items():
        r = obj['report']
        if any(r.get(k) != base.get(k) for k in keys) or r.get('device') != device:
            reasons.append('CROSS_REPORT_IDENTITY_MISMATCH_' + phase.upper().replace('-', '_'))
    if reasons:
        return {'status':'REJECTED', 'checks':{p:'REJECTED' if p in records else 'MISSING' for p in PHASES}, 'problems': sorted(set(reasons))}
    categories['baseline'] = 'RAW_DEVICE_PASS'
    post = (records.get('postboot') or {}).get('report', {})
    p = post.get('observations', {}).get('postboot', {})
    if post and check(post, 'postboot_recovery') and p.get('kernel_reboot_verified') is True and p.get('installed_binary_unchanged') is True and isinstance(p.get('monitor'), dict) and p['monitor'].get('elapsed_seconds', 0) >= 90:
        categories['postboot'] = 'RAW_DEVICE_PASS'
    else:
        categories['postboot'] = 'MISSING' if not post else 'UNVERIFIED'
    end = (records.get('endurance') or {}).get('report', {})
    en = end.get('observations', {}).get('endurance', {})
    counts = end.get('observations', {}).get('endurance_progress', {}).get('counts', {})
    if end and check(end, 'endurance') and en.get('elapsed_seconds', 0) >= 3600 and en.get('samples', 0) >= 100 and counts.get('healthy', 0) >= 100 and all(counts.get(k) == 0 for k in ('boot_id_changed', 'query_errors', 'unhealthy')):
        categories['endurance'] = 'RAW_DEVICE_PASS'
    else:
        categories['endurance'] = 'MISSING' if not end else 'UNVERIFIED'
    man = (records.get('manual') or {}).get('report', {})
    required_manual = ('webui_quick_actions', 'download_export', 'secondary_app_filemanager', 'wifi_offline_recovery', 'screen_lock_wake', 'accessibility')
    categories['manual'] = 'USER_REPORTED_PASS' if man and all(check(man, key, 'USER_REPORTED_PASS') for key in required_manual) else ('MISSING' if not man else 'UNVERIFIED')
    app = (records.get('app-probe') or {}).get('report', {})
    probe = app.get('observations', {}).get('ordinary_app_probe', {})
    if app and check(app, 'ordinary_app_read_write') and probe.get('package') == 'org.skybind.probe' and isinstance(probe.get('app_uid'), int) and 10000 <= probe['app_uid'] < 99000 and probe.get('write_bytes') == probe.get('read_bytes') == 32 and probe.get('read_matches') is True and probe.get('target_path_sha256') == base['mountpoint_sha256'] and reliable_hash(probe.get('nonce_sha256')) and probe.get('source') == 'installed_android_activity_private_receipt_not_run_as_simulation':
        categories['app-probe'] = 'RAW_DEVICE_PASS'
    else:
        categories['app-probe'] = 'MISSING' if not app else 'UNVERIFIED'
    return {'status': 'RAW_COMPLETE_NOT_ATTESTED' if all(categories[p] in ('RAW_DEVICE_PASS', 'USER_REPORTED_PASS') for p in PHASES) else 'RAW_INCOMPLETE', 'checks': categories, 'problems': (['PHYSICAL_DEVICE_INDEPENDENT_IDENTITY_NOT_VERIFIED'] if device.get('is_emulator') in ('', None) else [])}


def pick_session(archives: list[Path], chosen: str | None) -> tuple[str | None, dict, list]:
    groups: dict[str, dict] = {}
    rejected: list = []
    for path in sorted(archives):
        m = ZIP_NAME.fullmatch(path.name)
        if not m:
            continue
        phase = m[1]
        try:
            obj = load_zip(path)
            sid = obj['report']['session_id']
            if phase in groups.setdefault(sid, {}):
                raise EvidenceError('duplicate phase in session')
            groups[sid][phase] = obj
        except (EvidenceError, zipfile.BadZipFile, OSError) as exc:
            rejected.append({'file': path.name, 'reason': str(exc)})
    if chosen and chosen not in groups:
        raise EvidenceError('requested session has no valid evidence')
    session = chosen if chosen else (max(groups, key=lambda s: (len(groups[s]), s)) if groups else None)
    return session, groups.get(session, {}), rejected


def source_identity(root: Path) -> dict:
    def run(*args):
        proc = subprocess.run(['git', '-c', 'safe.directory=' + str(root), '-C', str(root), *args], text=True, capture_output=True, timeout=10, check=False)
        return proc.stdout.strip() if proc.returncode == 0 else None
    return {'commit': run('rev-parse','HEAD'), 'tree': run('rev-parse','HEAD^{tree}'), 'worktree_clean': run('status','--porcelain') == '', 'frozen_against_device_binary': False}


def evaluate_gates(root: Path) -> dict:
    # Delegate solely to the existing source-bound, external-trust-aware verifier.
    proc = subprocess.run([sys.executable, str(root/'scripts/dev/seal/sb_cfs1.py'), '--repository', str(root)], cwd=root, capture_output=True, text=True, timeout=90, check=False)
    try:
        obj = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {'status':'EVALUATOR_ERROR','final_seal':'NOT_ISSUED','milestone_gates':{},'reasons':['CFS1_NON_JSON_OUTPUT'], 'exit_code':proc.returncode}
    if proc.returncode not in (0,3) or obj.get('status') not in ('QUALIFIED','BLOCKED') or (proc.returncode==3 and obj.get('final_seal') != 'NOT_ISSUED'):
        return {'status':'EVALUATOR_ERROR','final_seal':'NOT_ISSUED','milestone_gates':{},'reasons':['CFS1_INCONSISTENT_RESULT'], 'exit_code':proc.returncode}
    return {'status': obj['status'], 'final_seal': obj['final_seal'], 'milestone_gates': obj.get('milestone_gates',{}), 'reasons': obj.get('reasons',[]), 'exit_code': proc.returncode}


def consolidate(root: Path, evidence: Path, session: str | None = None, candidate: Path | None = None) -> dict:
    if not evidence.is_dir():
        raise EvidenceError('evidence directory not found')
    sid, records, rejected = pick_session(list(evidence.glob('skybind-q09-*.zip')), session)
    # Reject same-session tampering; do not silently ignore a poisoned input.
    if sid and any(sid in x['file'] for x in rejected):
        raise EvidenceError('invalid evidence ZIP in selected session: ' + repr(rejected))
    raw = reconcile_session(records)
    build = {'candidate_sha256': None, 'candidate_name': None, 'source_to_installed_binding': 'NOT_PROVEN'}
    if candidate is not None:
        if candidate.is_symlink() or not candidate.is_file():
            raise EvidenceError('candidate must be a regular file')
        build.update(candidate_sha256=sha(candidate.read_bytes()), candidate_name=candidate.name)
    gate = evaluate_gates(root)
    sources = source_identity(root)
    return {'schema_version':1, 'campaign':'SB-Q11', 'product':'skybind',
            'status':'CONSOLIDATED_NOT_RELEASE_QUALIFIED',
            'assurance':'RAW_DEVICE_EVIDENCE_ONLY', 'final_seal':'NOT_ISSUED',
            'selected_session':sid, 'source':sources, 'build':build,
            'raw_evidence':raw,
            'archives':[{'phase':p, 'archive_sha256':records[p]['archive_sha256'], 'name':records[p]['basename']} for p in PHASES if p in records],
            'excluded_archives':rejected,
            'independent_gate_evaluation':gate,
            'next_obligations':['G01_G08_INDEPENDENT_SIGNED_GATE_EVIDENCE', 'SOURCE_CANDIDATE_DEVICE_BUILD_BINDING',
                                'BOTH_PROVIDERS_REPRODUCIBILITY', 'PHYSICAL_MANAGER_AND_NEGATIVE_SECURITY_MATRIX',
                                'ORIGINAL_WEBVIEW_BROWSER_ACCESSIBILITY_MATRIX', 'EXTERNAL_FINAL_SEAL'],
            'limitations':['Q09 files are user-collected raw evidence, not independent attestation',
                           'Checksums validate archive consistency, not authorship',
                           'Local git state and candidate hash are informational and do not attest the installed module',
                           'No gate is promoted and no release attestation is issued by Q11']}


def markdown(result: dict) -> str:
    lines = ['# Skybind SB-Q11 — Evidence Reconciliation', '',
             '**Release:** NOT_ISSUED  ',
             '**Assurance:** Raw device evidence; independent gate attestation required', '',
             'Selected session: `' + str(result['selected_session'] or 'none') + '`', '',
             '| Device check | Reconciled status |','|---|---|']
    lines.extend(f'| {p} | {result["raw_evidence"]["checks"].get(p,"MISSING")} |' for p in PHASES)
    lines += ['', '| Independent gate | Actual evaluator status |','|---|---|']
    lines.extend(f'| SB-G{i:02d} | {result["independent_gate_evaluation"]["milestone_gates"].get(f"SB-G{i:02d}","UNKNOWN")} |' for i in range(1,9))
    lines += ['', 'Q09 raw observations do not satisfy independent gate or final-seal obligations.', '', '## Remaining obligations', '']
    lines.extend('- ' + x for x in result['next_obligations'])
    lines += ['', 'The original source-bound `sb_cfs1.py` verifier is the sole authority used for gate state. This Q11 tool never signs, fabricates receipts, installs binaries, or changes source policy.', '']
    return '\n'.join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-dir', type=Path, default=Path(os.environ.get('SKYBIND_Q11_EVIDENCE_DIR', str(Path.home()/'storage/downloads'))))
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--session')
    parser.add_argument('--candidate', type=Path, help='Optional candidate ZIP hash (not an attestation)')
    parser.add_argument('--repository', type=Path, default=ROOT)
    a = parser.parse_args(argv)
    try:
        result = consolidate(a.repository.resolve(), a.evidence_dir, a.session, a.candidate)
        if a.output_dir:
            if a.output_dir.resolve().is_relative_to(a.repository.resolve()):
                raise EvidenceError('reports must not be stored inside source repository')
            a.output_dir.mkdir(parents=True, exist_ok=True)
            (a.output_dir/'skybind-q11-summary.json').write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
            (a.output_dir/'skybind-q11-summary.md').write_text(markdown(result))
        print(json.dumps(result, sort_keys=True))
        return 0
    except (EvidenceError, OSError, subprocess.TimeoutExpired) as exc:
        print('SB-Q11: '+str(exc), file=sys.stderr)
        return 2


if __name__=='__main__':
    sys.exit(main())
