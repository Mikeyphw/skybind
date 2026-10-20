#!/usr/bin/env python3
"""Read-only reconciliation of independent authenticated M3 device receipts.

This never triggers a device lane, builds an APK, modifies a job, or converts
narrow device scopes into whole-product release qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

SCOPES={
    'm3-preview-live': ('m3_preview_device_qualified', 'PASS_M3_REAL_DAEMON_PREVIEW_ONLY',
                        'M3_REAL_DAEMON_JOB_PREVIEW_ONLY_NO_EXECUTION'),
    'm3-execute-live': ('m3_execute_device_qualified', 'PASS_M3_DISPOSABLE_CHECK_COMPLETION',
                        'M3_DISPOSABLE_CHECK_START_TO_TERMINAL_EVENTS_ONLY'),
    'm3-cancel-live': ('m3_cancel_device_qualified', 'PASS_M3_DISPOSABLE_OWNED_CANCEL',
                       'M3_DISPOSABLE_SESSION_OWNED_CANCEL_ONLY'),
    'm3-copy-live': ('m3_copy_device_qualified', 'PASS_M3_DISPOSABLE_COPY_RECONCILED',
                     'M3_LOCAL_DISPOSABLE_COPY_SHA256_RECONNECT_TERMINAL_ONLY'),
}
SHA=re.compile(r'^[0-9a-f]{40}$')
class InvalidReceipt(ValueError):pass

def require(ok, reason):
    if not ok: raise InvalidReceipt(reason)

def load_bounded(path:Path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size<=512_000,
            'RECEIPT_NOT_REGULAR_BOUNDED_FILE')
    return json.loads(path.read_text())

def verify_summary(path:Path, native_root:Path):
    summary=load_bounded(path)
    require(summary.get('status')=='PASS_CI_PAIR_AND_SELECTED_LANES', 'SUMMARY_NOT_PASS')
    lanes=summary.get('selected_lanes')
    require(isinstance(lanes,list) and len(lanes)==1 and lanes[0] in SCOPES,
            'SUMMARY_NOT_ONE_M3_LANE')
    lane=lanes[0];flag,state,scope=SCOPES[lane]
    require(summary.get('installed_pair_verified') is True and
            summary.get('release_qualified',False) is False and
            summary.get('device_qualified',False) is False, 'SUMMARY_SCOPE_OR_APK_NOT_VALID')
    sha=summary.get('source_sha');run=summary.get('github_run_id');artifact=summary.get('artifact_id')
    require(isinstance(sha,str) and SHA.fullmatch(sha) and
            type(run) is int and run>0 and type(artifact) is int and artifact>0,
            'SUMMARY_BUILD_PROVENANCE_INVALID')
    require(summary.get(flag) is True, 'SUMMARY_LANE_NOT_QUALIFIED')
    row=summary.get('tests',{}).get(lane)
    require(isinstance(row,dict) and row.get('state')==state and
            row.get('qualified_scope')==scope, 'SUMMARY_TEST_SCOPE_MISMATCH')
    pointer=row.get('receipt')
    require(isinstance(pointer,str) and pointer, 'NATIVE_RECEIPT_MISSING')
    native_file=Path(pointer)
    require(native_file.parent.resolve()==native_root.resolve() and not native_file.is_symlink(),
            'NATIVE_RECEIPT_NOT_IN_EXPECTED_ROOT')
    native=load_bounded(native_file)
    require(native.get('schema')=='skybind-m2-live-v1' and
            native.get('source_sha')==sha and native.get('github_run_id')==run and
            native.get('artifact_id')==artifact and native.get('state')==state and
            native.get('qualified_scope')==scope and native.get(flag) is True and
            native.get('installed_pair_verified') is True and
            native.get('signing_verified') is True and
            native.get('release_qualified') is False and
            native.get('device_qualified') is False,
            'NATIVE_RECEIPT_PROVENANCE_OR_SCOPE_MISMATCH')
    # An independently verified COPY must include both signed preflight and
    # post-instrumentation content hash evidence, not just a passing label.
    if lane=='m3-copy-live':
        pre=native.get('copy_preflight');post=native.get('copy_integrity')
        require(isinstance(pre,dict) and isinstance(post,dict) and
                pre.get('source_verified') is True and post.get('source_verified') is True and
                post.get('destination_verified') is True and
                post.get('sentinel_preserved') is True and
                type(post.get('count')) is int and post['count']>0 and
                pre.get('count')==post['count'] and
                re.fullmatch('[0-9a-f]{64}',str(post.get('expected_content_sha256',''))) and
                pre.get('expected_content_sha256')==post.get('expected_content_sha256'),
                'COPY_INTEGRITY_EVIDENCE_INCOMPLETE')
    return {'lane':lane,'github_run_id':run,'artifact_id':artifact,
            'source_sha':sha,'scope':scope,'state':state,
            'summary_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'native_receipt_sha256':hashlib.sha256(native_file.read_bytes()).hexdigest()}

def reconcile(summaries:list[Path],native_root:Path):
    evidence={};skipped=[]
    for path in sorted(summaries):
        try:
            row=verify_summary(path,native_root)
        except (InvalidReceipt,ValueError,OSError,TypeError,KeyError) as e:
            skipped.append({'summary':str(path),'reason':str(e)[:120]})
            continue
        # Distinct lanes retain distinct source/build identity. Do not require
        # historical M3 preview and copy to share the latest commit.
        evidence[row['lane']]=row
    missing=sorted(set(SCOPES)-set(evidence))
    return {'schema':'skybind-m3-scoped-evidence-v1',
            'status':'PASS_FOUR_INDEPENDENT_M3_SCOPES' if not missing else 'BLOCKED_M3_EVIDENCE_INCOMPLETE',
            'qualified_scopes':evidence,'missing_scopes':missing,'invalid_or_unselected':skipped,
            'whole_m3_qualified':False,'external_provider_qualified':False,
            'release_qualified':False,'device_retests_run':False}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--summary',type=Path,action='append',default=[])
    p.add_argument('--summary-root',type=Path)
    p.add_argument('--native-root',type=Path,default=Path.home()/'.local/state/skybind/native-m2-live')
    p.add_argument('--output',type=Path)
    o=p.parse_args(argv)
    summaries=list(o.summary)
    if o.summary_root:
        require(o.summary_root.is_dir() and not o.summary_root.is_symlink(),'INVALID_SUMMARY_ROOT')
        summaries.extend(o.summary_root.glob('ci-*/summary.json'))
    require(len(summaries)<=4096, 'TOO_MANY_SUMMARIES')
    report=reconcile(summaries,o.native_root)
    blob=json.dumps(report,sort_keys=True,indent=2)+'\n'
    if o.output:
        require(o.output.parent.is_dir() and not o.output.exists(), 'OUTPUT_MUST_BE_NEW_FILE')
        o.output.write_text(blob)
    print(blob,end='')
    return 0 if not report['missing_scopes'] else 2

if __name__=='__main__':
    try:raise SystemExit(main())
    except (InvalidReceipt,OSError,ValueError) as e:
        print(json.dumps({'status':'BLOCKED','reason':str(e)[:150]},sort_keys=True))
        raise SystemExit(2)
