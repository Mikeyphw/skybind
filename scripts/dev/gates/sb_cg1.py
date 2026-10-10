#!/usr/bin/env python3
"""SB-CG1: independent, read-only G03..G08 evidence gates.

Successful definition tests are NOT gate promotion. Never create evidence, sign
an attestation, select a user-provided trust key without an external digest, or
use root-shell observations as ordinary-app proofs.
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

ROOT = Path(__file__).resolve().parents[3]
GATES = tuple(f'SB-G{i:02}' for i in range(3, 9))
PASS = {'SB-G03': 'HOST_LIFECYCLE_PASS', 'SB-G04': 'ANDROID_SOURCE_PASS',
        'SB-G05': 'BACKEND_FEATURE_PASS', 'SB-G06': 'TRANSPORT_SECURITY_PASS',
        'SB-G07': 'WEBUI_PARITY_PASS', 'SB-G08': 'DEVICE_RELEASE_READY'}
REQUIRES = {
    'SB-G03': ('SB-G02',),
    'SB-G04': ('SB-G03',),
    'SB-G05': ('SB-G03',),
    'SB-G06': ('SB-G02', 'SB-G04', 'SB-G05'),
    'SB-G07': ('SB-G06',),
    'SB-G08': ('SB-G01', 'SB-G02', 'SB-G03', 'SB-G04', 'SB-G05', 'SB-G06', 'SB-G07'),
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_digest(root: Path, source_paths: list[str]) -> str:
    """Stable scope hash; also fails when the source scope is missing."""
    digest = hashlib.sha256()
    count = 0
    for rel in sorted(source_paths):
        p = root / rel
        if not p.exists() or p.is_symlink():
            raise ValueError('source missing or symlink: ' + rel)
        descendants = [p] if p.is_file() else sorted(p.rglob('*'))
        if any(x.is_symlink() for x in descendants):
            raise ValueError('symlink in source scope: ' + rel)
        files = [x for x in descendants if x.is_file()]
        if not files:
            raise ValueError('empty source scope: ' + rel)
        for child in files:
            if any(part in ('.git', '__pycache__', 'build', 'dist') for part in child.relative_to(root).parts):
                continue
            relative = str(child.relative_to(root))
            digest.update(relative.encode() + b'\0' + sha(child.read_bytes()).encode() + b'\n')
            count += 1
    if not count:
        raise ValueError('no source files found')
    return digest.hexdigest()


def git_commit(root: Path) -> str:
    proc = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'], capture_output=True, text=True, timeout=10, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ''


def read_ledger(root: Path, gate: str) -> dict:
    p = root / 'docs' / 'gates' / (gate + '_PROMISE_LEDGER.json')
    d = json.loads(p.read_text())
    if d['schema_version'] != 1 or d['gate'] != gate or d['product'] != 'skybind':
        raise ValueError('ledger identity mismatch')
    if sorted(d['dependencies']) != sorted(json.loads((root/'docs/roadmap/SKYBIND_ORIGINAL_45_ITEM_INDEX.json').read_text())['gate_overlays'][int(gate[-2:])-1]['dependencies']):
        raise ValueError('ledger dependencies differ from original promises')
    if not d['negative_and_positive_checks'] or not d['source_paths']:
        raise ValueError('incomplete gate promise ledger')
    return d


def _verified_attestation(root: Path, gate: str, scope_hash: str, commit: str, ledger: dict) -> list[str]:
    """Only externally rooted, signed, immutable Devtool evidence can qualify.

    No trust/key/proof is created by the campaign, and none are embedded in the
    repository. A signature alone is insufficient: referenced raw run receipts
    must exist and match their digests, with two distinct Devtool run identities.
    """
    reasons = []
    base_text = os.environ.get('SKYBIND_VERIFIED_GATE_EVIDENCE_DIR', '')
    key_text = os.environ.get('SKYBIND_GATE_TRUST_PUBKEY', '')
    pin = os.environ.get('SKYBIND_GATE_TRUST_KEY_SHA256', '')
    if not base_text or not key_text or not re.fullmatch(r'[0-9a-f]{64}', pin):
        return ['INDEPENDENT_TRUST_AND_EVIDENCE_NOT_CONFIGURED']
    try:
        base = Path(base_text).resolve(strict=True)
        key = Path(key_text).resolve(strict=True)
        realroot = root.resolve(strict=True)
        if base.is_relative_to(realroot) or key.is_relative_to(realroot):
            return ['EVIDENCE_OR_TRUST_KEY_INSIDE_REPOSITORY']
        if not base.is_dir() or not key.is_file() or sha(key.read_bytes()) != pin:
            return ['TRUST_KEY_PIN_INVALID']
        gate_dir = base/gate
        manifest = gate_dir/'attestation.json'
        sig = gate_dir/'attestation.sig'
        if not manifest.is_file() or not sig.is_file() or manifest.is_symlink() or sig.is_symlink():
            return ['SIGNED_GATE_ATTESTATION_MISSING']
        verify = subprocess.run(['openssl','pkeyutl','-verify','-pubin','-inkey',str(key),
                                 '-rawin','-in',str(manifest),'-sigfile',str(sig)],
                                capture_output=True, timeout=12, check=False)
        if verify.returncode != 0:
            return ['INDEPENDENT_SIGNATURE_INVALID']
        obj = json.loads(manifest.read_bytes())
        if obj.get('schema_version') != 1 or obj.get('gate') != gate or obj.get('product') != 'skybind':
            reasons.append('SIGNED_SCHEMA_OR_GATE_INVALID')
        if obj.get('source_commit') != commit or obj.get('source_scope_sha256') != scope_hash:
            reasons.append('SIGNED_SOURCE_FREEZE_STALE')
        if obj.get('result') != 'PASS' or obj.get('warnings') != 0 or obj.get('unresolved_obligations') != []:
            reasons.append('SIGNED_CHECKS_NOT_CLEAN')
        if not set(ledger['negative_and_positive_checks']).issubset(set(obj.get('checks_passed', []))):
            reasons.append('SIGNED_NEGATIVE_CASE_COVERAGE_INCOMPLETE')
        ids = obj.get('devtool_run_ids', [])
        if not isinstance(ids,list) or len(ids)<2 or len(set(ids))!=len(ids) or any(not isinstance(x,str) or not re.fullmatch(r'[a-f0-9]{32}', x) for x in ids):
            reasons.append('INDEPENDENT_DEVTOOL_RUNS_MISSING')
            ids=[]
        # The independent reviewer must preserve source-bound, immutable raw
        # Devtool receipts. Two IDs written into a JSON assertion are not proof.
        receipts = obj.get('run_receipts', [])
        if not isinstance(receipts,list) or len(receipts)!=len(ids):
            reasons.append('RAW_DEVTOOL_RUN_RECEIPTS_MISSING')
        else:
            recorded=set()
            for item in receipts:
                if not isinstance(item,dict) or item.get('run_id') not in ids or item.get('run_id') in recorded:
                    reasons.append('RUN_RECEIPT_IDENTITY_INVALID');continue
                run_id=item['run_id'];recorded.add(run_id)
                rpath=gate_dir/'runs'/run_id/'run.json'
                if (rpath.is_symlink() or not rpath.is_file() or
                    not re.fullmatch(r'[a-f0-9]{64}',str(item.get('sha256',''))) or
                    sha(rpath.read_bytes())!=item['sha256']):
                    reasons.append('RUN_RECEIPT_HASH_INVALID');continue
                try:
                    run=json.loads(rpath.read_bytes())
                    if (run.get('run_id')!=run_id or run.get('gate')!=gate or
                        run.get('source_commit')!=commit or run.get('source_scope_sha256')!=scope_hash or
                        run.get('status')!='passed' or run.get('warnings')!=0 or
                        not set(ledger['negative_and_positive_checks']).issubset(set(run.get('tests_passed',[]))) or
                        run.get('provenance')!='independently_verified_devtool_run_store'):
                        reasons.append('RUN_RECEIPT_CONTENTS_UNQUALIFIED')
                except (ValueError,TypeError):reasons.append('RUN_RECEIPT_MALFORMED')
            if len(recorded)!=len(ids):reasons.append('RUN_RECEIPT_CLOSURE_INCOMPLETE')
        attachments = obj.get('attachments', [])
        if not isinstance(attachments,list) or len(attachments) < 2:
            reasons.append('RAW_EVIDENCE_ATTACHMENTS_MISSING')
        else:
            for rec in attachments:
                if not isinstance(rec,dict):
                    reasons.append('INVALID_ATTACHMENT_RECORD');continue
                name = rec.get('name')
                if not isinstance(name,str) or '/' in name or '\\' in name or name in ('.','..'):
                    reasons.append('ATTACHMENT_PATH_UNSAFE');continue
                loc=gate_dir/'attachments'/name
                if loc.is_symlink() or not loc.is_file() or not re.fullmatch(r'[a-f0-9]{64}',str(rec.get('sha256',''))) or sha(loc.read_bytes())!=rec['sha256']:
                    reasons.append('RAW_EVIDENCE_CHECKSUM_MISMATCH')
        evidence_kinds=set(obj.get('evidence_kinds', []))
        if gate=='SB-G07' and not {'reference_screenshots','browser_interactions','embedded_webview','accessibility'}.issubset(evidence_kinds):
            reasons.append('WEBUI_VISUAL_AND_ANDROID_EVIDENCE_MISSING')
        if gate=='SB-G08' and not {'verified_both_providers','physical_manager_matrix','ordinary_app_io','reboot_endurance','reproducible_release'}.issubset(evidence_kinds):
            reasons.append('PHYSICAL_DEVICE_AND_RELEASE_EVIDENCE_MISSING')
        # An external signature is necessary, but its contents still need all
        # independently verified raw evidence and categorical proof.
    except (OSError,ValueError,TypeError,KeyError,subprocess.TimeoutExpired) as exc:
        reasons.append('EVIDENCE_UNTRUSTWORTHY_'+type(exc).__name__)
    return sorted(set(reasons))


def external_gates(root: Path) -> dict:
    result = {}
    sys.path.insert(0,str(root/'scripts/dev/gates'))
    for gate, name, expected in [('SB-G01','sb_g01','SOURCE_BUILD_PASS'),('SB-G02','sb_g02','SOURCE_CONTROL_PASS')]:
        try:
            mod=__import__(name)
            status=mod.evaluate(root=root)['status']
            result[gate] = status if status == expected else 'BLOCKED'
        except (ValueError,KeyError,TypeError,OSError,ImportError) as exc:
            result[gate]='BLOCKED'
    return result


def evaluate_all(root: Path=ROOT) -> dict:
    root=root.resolve()
    gates=external_gates(root)
    output={}
    commit=git_commit(root)
    for gate in GATES:
        reasons=[]
        ledger=None
        try:
            ledger=read_ledger(root,gate)
            scope=source_digest(root,ledger['source_paths'])
        except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError) as exc:
            reasons.append('GATE_SOURCE_OR_LEDGER_INVALID_'+type(exc).__name__)
            scope=None
        for dep in REQUIRES[gate]:
            expected='SOURCE_BUILD_PASS' if dep=='SB-G01' else 'SOURCE_CONTROL_PASS' if dep=='SB-G02' else PASS[dep]
            if gates.get(dep) != expected:
                reasons.append('DEPENDENCY_BLOCKED_'+dep)
        if not commit:
            reasons.append('SOURCE_COMMIT_UNAVAILABLE')
        if scope and commit and ledger:
            reasons.extend(_verified_attestation(root,gate,scope,commit,ledger))
        status = PASS[gate] if not reasons else 'BLOCKED'
        gates[gate]=status
        output[gate]={'gate':gate,'status':status,'source_scope_sha256':scope,'source_commit':commit,
                      'reasons':sorted(set(reasons)),'assurance':ledger['assurance_ceiling'] if status!= 'BLOCKED' else 'NOT_ATTESTED',
                      'final_seal':'NOT_ISSUED'}
    return {'schema_version':1,'campaign':'skybind','package':'SB-CG1','status':'PASS' if all(x['status']!='BLOCKED' for x in output.values()) else 'BLOCKED',
            'dependency_gates':{key:gates[key] for key in ('SB-G01','SB-G02')},'gates':output,
            'final_seal':'NOT_ISSUED','android_device':'NOT_ATTESTED' if output['SB-G08']['status']=='BLOCKED' else 'REQUIRES_FINAL_SEAL_REVIEW'}


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--repository',type=Path,default=ROOT)
    ap.add_argument('--gate', choices=GATES)
    ap.add_argument('--check',action='store_true')
    args=ap.parse_args()
    result=evaluate_all(args.repository)
    print(json.dumps(result['gates'][args.gate] if args.gate else result,sort_keys=True,indent=2))
    return 3 if result['status']=='BLOCKED' or (args.gate and result['gates'][args.gate]['status']=='BLOCKED') else 0

if __name__=='__main__':
    raise SystemExit(main())
