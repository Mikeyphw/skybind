#!/usr/bin/env python3
"""Final *independent verifier*, not a signing/attestation producer.

This command never issues a certificate, creates evidence, or asserts that a
source-only Devtool validation qualifies a physical Android release. Genuine
qualification requires eight independently passing gates and an externally
signed, source- and candidate-bound final release attestation.
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
GATES = tuple(f'SB-G{i:02d}' for i in range(1, 9))
EXPECTED = dict(zip(GATES, ('SOURCE_BUILD_PASS', 'SOURCE_CONTROL_PASS',
    'HOST_LIFECYCLE_PASS','ANDROID_SOURCE_PASS','BACKEND_FEATURE_PASS',
    'TRANSPORT_SECURITY_PASS','WEBUI_PARITY_PASS','DEVICE_RELEASE_READY')))
REQUIRED_EVIDENCE = frozenset({
    'newfuture_independent_reproducible_builds', 'bclone_independent_reproducible_builds',
    'verified_provider_provenance', 'real_arm64_candidate_integrity',
    'magisk_kernelsu_kernelsu_next_apatch_matrix', 'ordinary_app_exact_target_nonce_io',
    'android_reboot_endurance_fault_matrix', 'owned_fuse_mount_lifecycle',
    'remote_jobs_rc_crypt_security', 'two_webui_transports',
    'visual_ux_accessibility_webview_parity', 'all_57_typed_operations',
    'no_critical_open_obligations', 'clean_independent_devtool_gates',
})
SEAL_STATUS = 'VERIFIED_EXTERNALLY_ISSUED'

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _git(root: Path, *args: str) -> str:
    p = subprocess.run(['git','-C',str(root),*args], capture_output=True,
                       text=True, timeout=10, check=False)
    return p.stdout.strip() if p.returncode == 0 else ''

def _inside(path: Path, root: Path) -> bool:
    return path == root or path.is_relative_to(root)

def _external_file(root: Path, base: Path, relative: str) -> Path:
    if not relative or '/' in relative or '\\' in relative or relative in ('.','..'):
        raise ValueError('unsafe evidence filename')
    file=base/relative
    if file.is_symlink() or not file.is_file() or _inside(file.resolve(strict=True),root):
        raise ValueError('unsafe evidence file')
    return file

def _verify_final_attestation(root: Path, *, commit: str, digest: str,
                              gate_results: dict) -> tuple[list[str], str | None]:
    """Validate out-of-repo, pinned-signature proof and its *raw* artifacts.

    No private key exists in Skybind; the verifier never generates seal files.
    """
    base_arg=os.environ.get('SKYBIND_FINAL_SEAL_EVIDENCE_DIR','')
    key_arg=os.environ.get('SKYBIND_FINAL_SEAL_PUBKEY','')
    pin=os.environ.get('SKYBIND_FINAL_SEAL_PUBKEY_SHA256','')
    if not base_arg or not key_arg or re.fullmatch(r'[a-f0-9]{64}',pin) is None:
        return ['FINAL_INDEPENDENT_TRUST_NOT_CONFIGURED'],None
    try:
        base=Path(base_arg).resolve(strict=True)
        key=Path(key_arg).resolve(strict=True)
        realroot=root.resolve(strict=True)
        if _inside(base,realroot) or _inside(key,realroot) or not base.is_dir():
            return ['FINAL_EVIDENCE_OR_KEY_INSIDE_REPOSITORY'],None
        if not key.is_file() or key.is_symlink() or sha(key.read_bytes())!=pin:
            return ['FINAL_TRUST_KEY_PIN_INVALID'],None
        evidence=base/'final-attestation.json'
        signature=base/'final-attestation.sig'
        if (not evidence.is_file() or evidence.is_symlink() or
            not signature.is_file() or signature.is_symlink()):
            return ['FINAL_SIGNED_ATTESTATION_MISSING'],None
        raw=evidence.read_bytes()
        result=subprocess.run(['openssl','pkeyutl','-verify','-pubin','-inkey',str(key),
                 '-rawin','-in',str(evidence),'-sigfile',str(signature)],
                 capture_output=True,timeout=12,check=False)
        if result.returncode: return ['FINAL_ATTESTATION_SIGNATURE_INVALID'],None
        obj=json.loads(raw)
        reasons=[]
        if not isinstance(obj,dict) or obj.get('schema_version')!=1 or obj.get('product')!='skybind':
            return ['FINAL_ATTESTATION_IDENTITY_INVALID'],None
        if obj.get('source_commit')!=commit or obj.get('source_tree_sha256')!=digest:
            reasons.append('FINAL_ATTESTATION_SOURCE_DRIFT')
        if obj.get('result')!='QUALIFIED' or obj.get('open_critical_obligations')!=[] or obj.get('warnings')!=0:
            reasons.append('FINAL_ATTESTATION_NOT_CLEAN')
        if obj.get('milestone_results')!={k:EXPECTED[k] for k in GATES} or any(gate_results.get(g)!=EXPECTED[g] for g in GATES):
            reasons.append('FINAL_ATTESTATION_GATE_MISMATCH')
        if not REQUIRED_EVIDENCE.issubset(set(obj.get('evidence_kinds',[]))):
            reasons.append('FINAL_EVIDENCE_COVERAGE_INCOMPLETE')
        # The candidate is checked against actual package bytes, not a label.
        candidate=obj.get('candidate')
        if not isinstance(candidate,dict):
            reasons.append('FINAL_CANDIDATE_UNSPECIFIED')
        else:
            name=candidate.get('filename')
            if not isinstance(name,str):
                reasons.append('FINAL_CANDIDATE_UNSAFE')
            else:
                try:
                    f=_external_file(realroot,base/'artifacts',name)
                    if (not re.fullmatch(r'[a-f0-9]{64}',str(candidate.get('sha256',''))) or
                        sha(f.read_bytes())!=candidate['sha256']):
                        reasons.append('FINAL_CANDIDATE_CHECKSUM_MISMATCH')
                except (OSError,ValueError):
                    reasons.append('FINAL_CANDIDATE_MISSING_OR_UNSAFE')
        receipts=obj.get('independent_receipts',[])
        if not isinstance(receipts,list) or len(receipts)<8:
            reasons.append('FINAL_RAW_RECEIPTS_MISSING')
        else:
            observed=set()
            for rec in receipts:
                if not isinstance(rec,dict) or rec.get('gate') not in GATES or rec.get('gate') in observed:
                    reasons.append('FINAL_RECEIPT_IDENTITY_INVALID');continue
                observed.add(rec['gate'])
                try:
                    f=_external_file(realroot,base/'receipts',rec.get('filename',''))
                    if sha(f.read_bytes())!=rec.get('sha256'):
                        reasons.append('FINAL_RECEIPT_HASH_MISMATCH');continue
                    item=json.loads(f.read_bytes())
                    if (item.get('gate')!=rec['gate'] or item.get('status')!=EXPECTED[rec['gate']] or
                        item.get('source_commit')!=commit or item.get('source_tree_sha256')!=digest):
                        reasons.append('FINAL_RECEIPT_CONTENTS_INVALID')
                except (OSError,ValueError,TypeError):
                    reasons.append('FINAL_RECEIPT_MISSING_OR_UNSAFE')
            if observed!=set(GATES): reasons.append('FINAL_GATE_RECEIPT_CLOSURE_INCOMPLETE')
        # Gate attestations, independent raw run-store evidence, and category
        # proofs are enforced by the separate SB-G01..G08 evaluators.
        if reasons: return sorted(set(reasons)),None
        return [],sha(raw)
    except (OSError,ValueError,TypeError,KeyError,subprocess.TimeoutExpired) as exc:
        return ['FINAL_EVIDENCE_UNTRUSTWORTHY_'+type(exc).__name__],None

def evaluate(root: Path=ROOT) -> dict:
    root=root.resolve()
    reasons=[]
    status={}
    commit=_git(root,'rev-parse','HEAD')
    tree=_git(root,'rev-parse','HEAD^{tree}')
    if not re.fullmatch(r'[a-f0-9]{40,64}',commit) or not re.fullmatch(r'[a-f0-9]{40,64}',tree):
        reasons.append('SOURCE_GIT_IDENTITY_MISSING')
    if _git(root,'status','--porcelain'):
        reasons.append('SOURCE_WORKTREE_NOT_CLEAN')
    try:
        plan=json.loads((root/'docs/roadmap/SKYBIND_DEVTOOL_OVERLAY_INDEX.json').read_bytes())
        original=json.loads((root/'docs/roadmap/SKYBIND_ORIGINAL_45_ITEM_INDEX.json').read_bytes())
        statuses=[a['status'] for a in plan['artifact_sequence']]
        if [a['id'] for a in plan['artifact_sequence']] != [f'SB-C{i:02d}' for i in range(1,7)]+['SB-CG1','SB-CFS1'] or statuses!=['SOURCE_IMPLEMENTED_NOT_PROMOTED']*8:
            reasons.append('FINAL_CAMPAIGN_DELIVERY_INCOMPLETE')
        if original['overlay_count']!=45 or original['typed_api_count']!=57 or len(plan['coverage_map'])!=34:
            reasons.append('FINAL_ORIGINAL_PROMISE_COVERAGE_INCOMPLETE')
        operations=json.loads((root/'internal/control/operations.json').read_bytes())
        canonical=json.loads((root/'docs/contracts/typed-operations.json').read_bytes())
        if operations['total']!=57 or operations['operations']!=canonical['operations']:
            reasons.append('FINAL_57_OPERATION_CATALOG_DRIFT')
        if not (root/'tests/fixtures/webui-reference/manifest.json').is_file():
            reasons.append('FINAL_ORIGINAL_WEBUI_REFERENCE_MISSING')
    except (KeyError,ValueError,TypeError,OSError) as exc:
        reasons.append('FINAL_SOURCE_INVENTORY_INVALID_'+type(exc).__name__)
    try:
        sys.path.insert(0,str(root/'scripts/dev/gates'))
        import sb_cg1, sb_g01, sb_g02
        r1=sb_g01.evaluate(root=root)
        r2=sb_g02.evaluate(root=root, g01_result=r1)
        others=sb_cg1.evaluate_all(root=root)
        status={'SB-G01':r1.get('status'),'SB-G02':r2.get('status')}
        status.update({gate:others['gates'][gate]['status'] for gate in sb_cg1.GATES})
        for gate in GATES:
            if status.get(gate)!=EXPECTED[gate]:
                reasons.append('FINAL_GATE_BLOCKED_'+gate)
        if others['final_seal']!='NOT_ISSUED':
            reasons.append('FINAL_GATE_EVALUATOR_PREMATURE_SEAL')
    except (OSError,ValueError,KeyError,TypeError,ImportError,subprocess.TimeoutExpired) as exc:
        reasons.append('FINAL_GATE_EVALUATION_UNAVAILABLE_'+type(exc).__name__)
    seal_digest=None
    if len(status)==8 and commit and tree:
        verified,seal_digest=_verify_final_attestation(root,commit=commit,digest=tree,gate_results=status)
        reasons.extend(verified)
    else: reasons.append('FINAL_INDEPENDENT_VERIFICATION_UNAVAILABLE')
    if any(status.get(k)!=EXPECTED[k] for k in GATES):
        seal_digest=None
    return {'schema_version':1,'campaign':'skybind','artifact':'SB-CFS1',
            'status':'QUALIFIED' if not reasons else 'BLOCKED',
            'milestone_gates':{k:status.get(k,'BLOCKED') for k in GATES},
            'source_commit':commit or None,'source_tree_sha256':tree or None,
            'final_seal':SEAL_STATUS if not reasons else 'NOT_ISSUED',
            'final_attestation_sha256':seal_digest if not reasons else None,
            'reasons':sorted(set(reasons)),
            'note':'An externally signed seal is verified, never generated by this source overlay.'}

def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument('--repository',type=Path,default=ROOT)
    args=parser.parse_args()
    result=evaluate(args.repository)
    print(json.dumps(result,sort_keys=True,indent=2))
    return 0 if result['status']=='QUALIFIED' else 3
if __name__=='__main__':
    raise SystemExit(main())
