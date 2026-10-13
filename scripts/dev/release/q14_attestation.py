#!/usr/bin/env python3
"""SB-Q14: authenticate CI run metadata, fetch and hash original candidates,
optionally verify GitHub-signed SLSA provenance. Never promote CFS1 gates.

GitHub CLI is the trust-boundary implementation; a receipt is NOT a signature.
This tool does not elevate a CI attestation to independent G01-G08 evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts/dev/release'))
import q13_reproducibility as q13
import q14_private_signing as private_sign

SHA = re.compile(r'[a-f0-9]{40}\Z')
REPO = re.compile(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z')
PROVIDERS = ('newfuture', 'bclone')
WORKFLOWS = {
    'skybind-q13-candidate-reproducibility.yml': 'skybind-q13-candidate-',
    'skybind-q14-attested-candidates.yml': 'skybind-q14-candidate-',
}
MAX_JSON = 2 * 1024 * 1024


def execute(args: list[str], *, limit: int = MAX_JSON, timeout: int = 180) -> str:
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       text=True, timeout=timeout, check=False)
    if p.returncode:
        raise RuntimeError('COMMAND_FAILED_' + str(p.returncode) + '_' + args[1].upper().replace('-', '_'))
    if len(p.stdout) > limit:
        raise ValueError('CLI_JSON_OUTPUT_TOO_LARGE')
    return p.stdout


def as_json(raw: str) -> dict:
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise ValueError('expected JSON object')
    return obj


def authenticated_run(repo: str, number: int) -> dict:
    if not REPO.fullmatch(repo) or number <= 0:
        raise ValueError('invalid repository or run ID')
    run = as_json(execute(['gh', 'api', f'repos/{repo}/actions/runs/{number}']))
    wf_id = run.get('workflow_id')
    if run.get('id') != number or not isinstance(wf_id, int):
        raise ValueError('GITHUB_RUN_IDENTITY_MISMATCH')
    wf = as_json(execute(['gh', 'api', f'repos/{repo}/actions/workflows/{wf_id}']))
    path = wf.get('path', '')
    basename = path.rsplit('/', 1)[-1]
    if path != f'.github/workflows/{basename}' or basename not in WORKFLOWS:
        raise ValueError('UNRECOGNIZED_WORKFLOW_IDENTITY')
    sha = run.get('head_sha')
    if not isinstance(sha, str) or not SHA.fullmatch(sha):
        raise ValueError('INVALID_GITHUB_HEAD_SHA')
    if run.get('status') != 'completed' or run.get('conclusion') != 'success':
        raise ValueError('GITHUB_RUN_NOT_SUCCESSFUL')
    repository = run.get('repository') or {}
    if repository.get('full_name', '').casefold() != repo.casefold():
        raise ValueError('RUN_REPOSITORY_MISMATCH')
    if run.get('event') != 'workflow_dispatch':
        raise ValueError('UNEXPECTED_RUN_EVENT')
    attempt = run.get('run_attempt', 1)
    if not isinstance(attempt, int) or attempt < 1:
        raise ValueError('INVALID_GITHUB_RUN_ATTEMPT')
    return {'run_id': number, 'run_attempt': attempt, 'repository': repository['full_name'], 'head_sha': sha,
            'workflow': basename, 'workflow_path': path, 'html_url': run.get('html_url', ''),
            'metadata_source': 'AUTHENTICATED_GITHUB_API', 'conclusion': 'success'}


def fetch_lanes(repo: str, number: int, prefix: str, folder: Path) -> tuple[Path, Path]:
    lanes = []
    for label in ('A', 'B'):
        path = folder / ('lane-' + label)
        if path.exists():
            raise ValueError('FRESH_DOWNLOAD_DIRECTORY_REQUIRED')
        path.mkdir(mode=0o700)
        execute(['gh', 'run', 'download', str(number), '-R', repo, '--name', prefix + label,
                 '--dir', str(path)], limit=4096, timeout=600)
        # Reject unexpected files, links and nested extras. q13 additionally validates exact
        # source receipt, names, provider ZIPs, and ZIP member provenance.
        allowed = {'candidate-evidence.json'} | {f'skybind-{v}-CANDIDATE-UNQUALIFIED.zip' for v in PROVIDERS}
        if prefix == 'skybind-q14-candidate-':
            allowed |= {private_sign.MANIFEST, private_sign.SIGNATURE, private_sign.PUBLIC}
        found = {p.name for p in path.iterdir()}
        if found != allowed or any(not p.is_file() or p.is_symlink() for p in path.iterdir()):
            raise ValueError('UNEXPECTED_CI_LANE_CONTENTS')
        if any(p.stat().st_size > 450 * 1024 * 1024 for p in path.iterdir()):
            raise ValueError('OVERSIZED_CANDIDATE')
        lanes.append(path)
    return lanes[0], lanes[1]


def valid_lane(lane: dict, head_sha: str) -> bool:
    receipt = lane.get('build_source') or {}
    return (lane.get('status') == 'VALID_UNQUALIFIED_LANE'
            and receipt.get('commit') == head_sha
            and receipt.get('git_clean') is True
            and all(lane['providers'][name].get('status') == 'VALID_UNQUALIFIED_CANDIDATE'
                    for name in PROVIDERS))


def validated_subjects(output: object, digest: str) -> bool:
    if not isinstance(output, list) or not output:
        return False
    for obj in output:
        if not isinstance(obj, dict):
            continue
        vr = obj.get('verificationResult') or {}
        statement = vr.get('statement') or {}
        if statement.get('predicateType') != 'https://slsa.dev/provenance/v1':
            continue
        for subject in statement.get('subject', []):
            if isinstance(subject, dict) and subject.get('digest', {}).get('sha256') == digest:
                return True
    return False


def attest(repo: str, run: dict, lane_dir: Path, provider: str, *, cli=execute) -> dict:
    filename = f'skybind-{provider}-CANDIDATE-UNQUALIFIED.zip'
    original = lane_dir / filename
    digest = q13.sha(original)
    out = {'candidate_sha256': digest, 'status': 'SIGNATURE_NOT_VERIFIED'}
    # 'gh attestation verify' handles Sigstore roots/cert validation, not this Python script.
    # Require exact repo, source digest, signer workflow, hosted runners and SLSA v1.
    args = ['gh', 'attestation', 'verify', str(original), '--repo', repo,
            '--signer-workflow', f'{repo}/.github/workflows/{run["workflow"]}',
            '--source-digest', run['head_sha'], '--deny-self-hosted-runners', '--format', 'json']
    try:
        claims = json.loads(cli(args))
        if not validated_subjects(claims, digest):
            out['status'] = 'SIGNATURE_OUTPUT_SUBJECT_MISMATCH'
        else:
            out['status'] = 'GH_SIGNED_SOURCE_AND_SUBJECT_VERIFIED_NOT_CFS1'
            out['verification'] = 'GITHUB_CLI_SIGSTORE_SLSA1_SIGNATURE_VERIFIED'
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired, json.JSONDecodeError):
        out['status'] = ('NO_Q13_ATTESTATIONS_EXPECTED' if
                         run['workflow'] == 'skybind-q13-candidate-reproducibility.yml'
                         else 'ATTESTATION_UNAVAILABLE_OR_REJECTED')
    return out


def private_signature_result(repo: str, run: dict, lane_dir: Path, lane: str,
                             trust_key: Path | None) -> dict:
    if trust_key is None or not trust_key.is_file() or trust_key.is_symlink():
        return {'status': 'EXTERNAL_PUBLIC_TRUST_ANCHOR_NOT_CONFIGURED', 'independent_attestation': False}
    try:
        if trust_key.resolve(strict=True).is_relative_to(lane_dir.resolve(strict=True)):
            return {'status': 'UNTRUSTED_DOWNLOADED_PUBLIC_KEY_REJECTED', 'independent_attestation': False}
        return private_sign.verify(lane_dir, trust_key, repo=repo, head_sha=run['head_sha'],
                                   run_id=run['run_id'], attempt=run['run_attempt'], lane=lane)
    except (ValueError, OSError, KeyError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        return {'status': 'PRIVATE_SIGNATURE_REJECTED', 'reason': type(exc).__name__ + ': ' + str(exc)[:140],
                'independent_attestation': False}


def local_evaluate(repo: str, number: int, root: Path, download_dir: Path,
                   trusted_public_key: Path | None = None) -> dict:
    run = authenticated_run(repo, number)
    folder = download_dir / f'skybind-q14-run-{number}'
    # New-run-only: never accidentally read old files or partially fetched lanes.
    if folder.exists() or folder.is_symlink():
        raise ValueError('RUN_EVIDENCE_DIRECTORY_EXISTS_MOVE_OR_REMOVE_MANUALLY')
    folder.mkdir(mode=0o700)
    lane_a, lane_b = fetch_lanes(repo, number, WORKFLOWS[run['workflow']], folder)
    a = q13.inspect_lane(lane_a, root)
    b = q13.inspect_lane(lane_b, root)
    if not valid_lane(a, run['head_sha']) or not valid_lane(b, run['head_sha']):
        raise ValueError('BUILD_RECEIPT_RUN_SHA_OR_PROVIDER_MISMATCH')
    parity = q13.same_provider(a, b)
    cross = [q13.cross_provider(x) for x in (a, b)]
    if (any(p['status'] != 'BYTE_IDENTICAL_UNATTESTED' for p in parity.values())
            or any(x['status'] != 'SHARED_PAYLOAD_MATCH_UNATTESTED' for x in cross)):
        raise ValueError('REPRODUCIBILITY_OR_CROSS_PROVIDER_PARITY_FAILED')
    if run['workflow'] == 'skybind-q14-attested-candidates.yml':
        lane_signatures = {label: private_signature_result(repo, run, lane_path, label, trusted_public_key)
                           for label, lane_path in (('A', lane_a), ('B', lane_b))}
        signatures = {label: {provider: dict(lane_signatures[label], candidate_sha256=lane['providers'][provider]['sha256'])
                              for provider in PROVIDERS}
                      for label, lane in (('A', a), ('B', b))}
        all_private_verified = all(x['status'] == 'PRIVATE_ED25519_SIGNATURE_VERIFIED_NOT_CFS1'
                                   for x in lane_signatures.values())
    else:
        signatures = {label: {provider: attest(repo, run, lane_path, provider) for provider in PROVIDERS}
                      for label, lane_path in (('A', lane_a), ('B', lane_b))}
        all_private_verified = False
    gates, final = q13.gate_diagnostics(root)
    return {'schema_version': 1, 'campaign': 'SB-Q14', 'status': 'CI_EVIDENCE_VERIFIED_GATES_UNQUALIFIED',
            'run': run, 'lanes': {'A': a, 'B': b},
            'same_provider': parity, 'cross_provider': cross,
            'signed_candidate_provenance': signatures,
            'all_four_attested': False, 'private_ci_signatures_verified': all_private_verified,
            'independent_attestation': False,
            'independent_gate_evaluation': gates,
            'cfs1_evaluation': final,
            'independent_gates_promoted': False,
            'final_seal': 'NOT_ISSUED',
            'limits': ['Q13 run predates signatures; old builds cannot retroactively acquire attestations',
                       'Private Ed25519 signer is maintainer-controlled and does not prove independent custody',
                       'Q14R2 requires an external pinned public key; downloaded public keys are not trusted by default',
                       'GitHub-signed CI provenance alone does not establish independent CFS1 gate receipts',
                       'Raw Q09 device evidence is not independently signed or a gate substitute',
                       'Candidates are UNQUALIFIED and never installed by this tool']}


def markdown(d: dict) -> str:
    lines = ['# Skybind SB-Q14 — Original GitHub artifacts and provenance', '',
             '**Final seal: NOT_ISSUED** · CFS1 remains authoritative.', '',
             'Run: `' + str(d['run']['run_id']) + '` · `' + d['run']['workflow'] + '`', '',
             '| Provider | A/B original candidate bytes | Lane A signature | Lane B signature |',
             '|---|---|---|---|']
    for p in PROVIDERS:
        lines.append('| '+p+' | '+d['same_provider'][p]['status']+' | '
                     +d['signed_candidate_provenance']['A'][p]['status']+' | '
                     +d['signed_candidate_provenance']['B'][p]['status']+' |')
    lines += ['', '## Original CFS1 release gates', '']
    for key, val in sorted(d['independent_gate_evaluation'].items()):
        lines.append('- '+key+': '+val['status']+' — '+', '.join(val.get('reasons', [])))
    lines += ['', 'Private CI signature validation requires the external owner-pinned Ed25519 public key.',
              'The GitHub artifact transport and signature verifier are separate from the independent CFS1 gate authority.',
              'Neither raw byte equality nor a GitHub OIDC attestation causes G01-G08 gate promotion.', '']
    return '\n'.join(lines)


def save(out: Path, filename: str, payload: bytes) -> None:
    if out.is_symlink() or not out.is_dir():
        raise ValueError('output directory missing or linked')
    path = out / filename
    if path.is_symlink():
        raise ValueError('output target symlink')
    fd, temp = tempfile.mkstemp(dir=str(out), prefix='.skybind-q14-')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo', default='Mikeyphw/skybind')
    ap.add_argument('--trusted-public-key', type=Path,
                    default=Path.home()/'.config/skybind/trust/q14-ci-public.pem')
    ap.add_argument('--run-id', type=int, required=True)
    ap.add_argument('--repository', type=Path, default=ROOT)
    ap.add_argument('--output-dir', type=Path, default=Path('/storage/emulated/0/Download'))
    args = ap.parse_args(argv)
    try:
        if not shutil.which('gh'):
            raise RuntimeError('gh CLI not installed')
        report = local_evaluate(args.repo, args.run_id, args.repository, args.output_dir, args.trusted_public_key)
        save(args.output_dir, 'skybind-q14-summary.json', (json.dumps(report, indent=2, sort_keys=True)+'\n').encode())
        save(args.output_dir, 'skybind-q14-summary.md', markdown(report).encode())
        print('SB-Q14R2 ORIGINAL_CANDIDATES_MATCH; PRIVATE_CI_SIGNATURE_STATUS_REPORTED; NOT_ISSUED')
        return 0
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        print('SB-Q14 BLOCKED: '+str(exc)[:220], file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
